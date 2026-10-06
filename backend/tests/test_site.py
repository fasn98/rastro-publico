"""Site estático: exportação, verificação antes de publicar, publicação e reversão."""

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import carregar
from rastro import publicacao, site
from rastro.api.main import app
from rastro.coletores import ibge
from rastro.db import get_session
from rastro.models import Coleta, Municipio
from rastro.politicos.modelos import PolEmenda, PolPolitico


def _secoes(dados: Path, arquivo: dict) -> list[dict]:
    return [
        json.loads((dados / s["ref"]).read_text()) if "ref" in s else s
        for s in arquivo["representantes"]["secoes"]
    ]


def _trava(monkeypatch, nome: str, valor: str) -> None:
    from rastro.config import get_settings

    monkeypatch.setenv(nome, valor)
    get_settings.cache_clear()


@pytest.fixture
def banco(session):
    session.add_all(Municipio(**ibge.normalizar(m)) for m in carregar("ibge_municipios.json"))
    session.commit()
    return session


@pytest.fixture
def exportado(banco, tmp_path):
    dados = tmp_path / "dist" / "dados"
    manifesto = site.exportar(dados, "SP", banco)
    (tmp_path / "dist" / "index.html").write_text("<!doctype html><title>Rastro</title>")
    return tmp_path / "dist", manifesto


def test_exporta_o_mesmo_que_a_api(banco, exportado):
    dist, manifesto = exportado
    dados = dist / "dados"
    lista = json.loads((dados / "municipios.json").read_text())
    # só SP: o fixture tem 2 municípios de SP e 1 de MT
    assert sorted(m["nome"] for m in lista) == ["Adamantina", "São Paulo"]
    assert manifesto["contagens"]["municipios"] == 2
    app.dependency_overrides[get_session] = lambda: banco
    try:
        api = TestClient(app)
        arquivo = json.loads((dados / "municipios" / "3550308.json").read_text())
        assert arquivo["detalhe"] == api.get("/api/municipios/3550308").json()
        assert arquivo["serie"] == api.get("/api/entes/3550308/indicadores/serie").json()
        rep = api.get("/api/municipios/3550308/representantes").json()
        assert arquivo["representantes"]["municipio"] == rep["municipio"]
        assert _secoes(dados, arquivo) == rep["secoes"]
        # seções de estado/federal iguais nos dois municípios -> um arquivo só, por referência
        outro = json.loads((dados / "municipios" / "3500105.json").read_text())
        refs = [s["ref"] for s in arquivo["representantes"]["secoes"] if "ref" in s]
        assert refs and refs == [s["ref"] for s in outro["representantes"]["secoes"] if "ref" in s]
    finally:
        app.dependency_overrides.clear()
    assert (dados / "metodologia.json").exists()
    assert site.verificar(dados) == []


def _politico(**campos) -> PolPolitico:
    base = {"partido": "X", "uf": "SP", "url_fonte": "https://exemplo.gov.br/registro"}
    return PolPolitico(**{**base, **campos})


@pytest.fixture
def com_politicos(banco):
    banco.add_all(
        [
            _politico(
                id=1, fonte="camara", id_fonte="1", nome="Dep Federal",
                cargo="deputado_federal", em_exercicio=True,
            ),
            _politico(
                id=2, fonte="tse", id_fonte="2", nome="Vereadora 2024", cargo="vereador",
                cod_ibge=3550308, eleicao_ano=2024,
            ),
            _politico(
                id=3, fonte="tse", id_fonte="3", nome="Governador 2026", cargo="governador",
                eleicao_ano=2026,
            ),
        ]
    )  # fmt: skip
    banco.flush()
    banco.add(Coleta(fonte="pol-emendas", status="sucesso"))
    banco.add(
        PolEmenda(
            codigo_emenda="E1", ano=2025, nome_autor="DEP FEDERAL", politico_id=1,
            cod_ibge_destino=3550308, valor_pago=10, url_fonte="https://exemplo.gov.br/e1",
        )
    )  # fmt: skip
    banco.commit()
    return banco


@pytest.mark.parametrize(
    ("tse", "tse_2026", "emendas", "esperados"),
    [
        ("0", "0", "0", {1}),
        ("1", "0", "0", {1, 2}),
        ("1", "1", "1", {1, 2, 3}),
    ],
)
def test_travas_desligadas_nao_vao_para_o_site(
    com_politicos, tmp_path, monkeypatch, tse, tse_2026, emendas, esperados
):
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE", tse)
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE_2026", tse_2026)
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_EMENDAS", emendas)
    dados = tmp_path / "dados"
    manifesto = site.exportar(dados, "SP", com_politicos)
    exportados = {int(p.stem) for p in (dados / "politicos").glob("*.json")}
    assert exportados == esperados
    assert manifesto["travas"] == {
        "pol_publicar_tse": tse == "1",
        "pol_publicar_tse_2026": tse_2026 == "1",
        "pol_publicar_emendas": emendas == "1",
    }
    texto = "".join(p.read_text() for p in dados.rglob("*.json"))
    assert ("Vereadora 2024" in texto) == (tse == "1")
    assert ("Governador 2026" in texto) == (tse_2026 == "1")
    municipio = json.loads((dados / "municipios" / "3550308.json").read_text())
    assert bool(municipio["emendas"]["itens"]) == (emendas == "1")
    emendas_pol = json.loads((dados / "politicos" / "1" / "emendas" / "todos.json").read_text())
    assert emendas_pol["publicadas"] == (emendas == "1")
    # todo político citado nas páginas dos municípios tem página própria
    assert site.verificar(dados) == []


def test_verificacao_recusa_dado_travado_no_arquivo(com_politicos, tmp_path, monkeypatch):
    """Segunda barreira: mesmo que algo travado escape da API, a publicação é recusada."""
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE", "0")
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE_2026", "0")
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_EMENDAS", "0")
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", com_politicos)
    (dados / "politicos" / "3.json").write_text(
        json.dumps({"id": 3, "fonte": "tse", "eleicao_ano": 2026})
    )
    (dados / "politicos" / "1" / "emendas" / "todos.json").write_text(
        json.dumps({"publicadas": True, "itens": [{"codigo_emenda": "E1"}], "totais": []})
    )
    problemas = site.verificar(dados)
    assert any("3.json" in p and "pol_publicar_tse_2026" in p for p in problemas)
    assert any("politicos/1/emendas/todos.json" in p for p in problemas)


def test_verificacao_recusa_politico_citado_sem_pagina(com_politicos, tmp_path):
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", com_politicos)
    (dados / "politicos" / "1.json").unlink()
    assert any("citados sem página" in p for p in site.verificar(dados))


def test_verificacao_bloqueia_dados_faltando(exportado):
    dist, manifesto = exportado
    dados = dist / "dados"
    anterior = {**manifesto, "contagens": {**manifesto["contagens"], "municipios": 645}}
    assert site.verificar(dados, anterior) == ["municipios: 2 na nova versão, 645 na publicada"]
    (dados / "municipios" / "3550308.json").unlink()
    assert "1 municípios sem arquivo de detalhe" in site.verificar(dados)
    (dados / "ranking_quebrado.json").write_text("{nao é json")
    assert any("JSON inválido" in p for p in site.verificar(dados))


# --- publicação (contra um repositório git local, sem rede) -------------------------------


@pytest.fixture
def remoto(tmp_path):
    caminho = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "-q", "--bare", str(caminho)], check=True)
    return str(caminho)


def _ls(remoto: str, *args) -> str:
    return subprocess.run(
        ["git", "ls-remote", *args, remoto], capture_output=True, text=True, check=True
    ).stdout


def _ramo(remoto):
    saida = _ls(remoto, "--heads").strip()
    return saida.split("\t")[0] if saida else None


def test_publica_guarda_5_e_reverte(exportado, remoto):
    dist, _ = exportado
    tags = [
        publicacao.publicar(dist, remoto, agora=datetime(2026, 10, d, 3, tzinfo=UTC))
        for d in range(1, 8)
    ]
    assert tags[-1] == "site-20261007-030000"
    publicadas = [p["tag"] for p in publicacao.listar(remoto)]
    assert publicadas == sorted(tags, reverse=True)[:5]  # só as 5 mais recentes
    no_ar = [p["tag"] for p in publicacao.listar(remoto) if p["no_ar"]]
    assert no_ar == ["site-20261007-030000"]

    # o site publicado tem o conteúdo e o .nojekyll, num commit sem histórico
    clone = Path(remoto).parent / "clone"
    subprocess.run(["git", "clone", "-q", "-b", "gh-pages", remoto, str(clone)], check=True)
    assert (clone / ".nojekyll").exists() and (clone / "dados" / "manifesto.json").exists()
    historico = subprocess.run(
        ["git", "-C", str(clone), "rev-list", "--count", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    assert historico == "1"

    # reverter sem argumento: volta para a anterior
    assert publicacao.reverter(remoto) == "site-20261006-030000"
    assert [p["tag"] for p in publicacao.listar(remoto) if p["no_ar"]] == ["site-20261006-030000"]
    # e de novo: a anterior à que está no ar agora
    assert publicacao.reverter(remoto) == "site-20261005-030000"
    # para uma tag específica
    assert publicacao.reverter(remoto, para="site-20261007-030000") == "site-20261007-030000"
    with pytest.raises(publicacao.ErroPublicacao, match="não existe"):
        publicacao.reverter(remoto, para="site-20200101-000000")


def test_publicacao_com_dados_faltando_nao_altera_o_site(exportado, remoto, tmp_path):
    dist, _ = exportado
    publicacao.publicar(dist, remoto, agora=datetime(2026, 10, 1, tzinfo=UTC))
    antes = _ramo(remoto)

    menor = tmp_path / "menor"
    shutil.copytree(dist, menor)
    lista = json.loads((menor / "dados" / "municipios.json").read_text())[:1]
    (menor / "dados" / "municipios.json").write_text(json.dumps(lista))
    m = json.loads((menor / "dados" / "manifesto.json").read_text())
    m["contagens"]["municipios"] = 1
    (menor / "dados" / "manifesto.json").write_text(json.dumps(m))

    with pytest.raises(publicacao.ErroPublicacao, match="municipios: 1 na nova versão, 2"):
        publicacao.publicar(menor, remoto, agora=datetime(2026, 10, 2, tzinfo=UTC))
    assert _ramo(remoto) == antes  # tudo ou nada: nada foi enviado
    assert len(publicacao.listar(remoto)) == 1


def test_token_nunca_aparece_em_mensagens():
    token = "github_pat_SEGREDO123"
    with pytest.raises(publicacao.ErroPublicacao) as erro:
        publicacao.listar("https://127.0.0.1:9/repo-inexistente.git", token)
    assert token not in str(erro.value)
    assert "***" in str(erro.value) or "127.0.0.1" in str(erro.value)


def test_eleito_do_tse_so_tem_o_arquivo_de_detalhe(com_politicos, tmp_path, monkeypatch):
    """Eleitos do TSE não têm listas (proposições, votos...): só o detalhe é exportado."""
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE", "1")
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", com_politicos)
    assert (dados / "politicos" / "2.json").exists()
    assert not (dados / "politicos" / "2").exists()
    assert (dados / "politicos" / "1" / "emendas" / "todos.json").exists()
    assert site.verificar(dados) == []
