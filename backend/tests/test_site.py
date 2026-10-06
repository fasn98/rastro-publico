"""Site estático: exportação, verificação antes de publicar, publicação e reversão."""

import gzip
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import carregar
from rastro import publicacao, site
from rastro.api.main import app
from rastro.coletores import ibge
from rastro.db import get_session
from rastro.models import Coleta, Municipio, PayloadBruto, RespostaBruta
from rastro.politicos.modelos import (
    PolDespesaCota,
    PolEmenda,
    PolPolitico,
    PolPresenca,
    PolVotacao,
)


def _secoes(dados: Path, arquivo: dict) -> list[dict]:
    return [
        json.loads((dados / s["ref"]).read_text()) if "ref" in s else s
        for s in arquivo["representantes"]["secoes"]
    ]


def _resumidas(secoes: list[dict]) -> list[dict]:
    """Seções da API como o site as grava: de cada político, só nome, partido e link."""
    return [
        {
            **sec,
            "grupos": [
                {**g, "politicos": [site._resumo_politico(p) for p in g["politicos"]]}
                for g in sec["grupos"]
            ],
        }
        for sec in secoes
    ]


def _eleitos(dados: Path) -> dict[int, dict]:
    return {
        p["id"]: p
        for arq in (dados / "eleitos").glob("*.json")
        for p in site.expandir(json.loads(arq.read_text()))
    }


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
        assert _secoes(dados, arquivo) == _resumidas(rep["secoes"])
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
    exportados = {int(p.stem) for p in (dados / "politicos").glob("*.json")} | set(_eleitos(dados))
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
    detalhe = json.loads((dados / "politicos" / "1.json").read_text())
    assert detalhe["emendas"]["publicadas"] == (emendas == "1")
    assert detalhe["emendas"]["anos"] == ([2025] if emendas == "1" else [])
    assert (dados / "politicos" / "1" / "emendas" / "2025.json").exists() == (emendas == "1")
    # todo político citado nas páginas dos municípios tem página própria
    assert site.verificar(dados) == []


def test_verificacao_recusa_dado_travado_no_arquivo(com_politicos, tmp_path, monkeypatch):
    """Segunda barreira: mesmo que algo travado escape da API, a publicação é recusada."""
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE", "0")
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE_2026", "0")
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_EMENDAS", "0")
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", com_politicos)
    (dados / "eleitos").mkdir(exist_ok=True)
    (dados / "eleitos" / "uf-SP-2026.json").write_text(
        json.dumps({"itens": [{"id": 3, "fonte": "tse", "eleicao_ano": 2026}]})
    )
    (dados / "politicos" / "1" / "emendas").mkdir(parents=True, exist_ok=True)
    (dados / "politicos" / "1" / "emendas" / "2025.json").write_text(
        json.dumps({"publicadas": True, "itens": [{"codigo_emenda": "E1"}], "totais": []})
    )
    problemas = site.verificar(dados)
    assert any("uf-SP-2026.json" in p and "pol_publicar_tse_2026" in p for p in problemas)
    assert any("politicos/1/emendas/2025.json" in p for p in problemas)
    assert any("fora do índice" in p for p in problemas)


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
    assert not (dados / "politicos" / "2.json").exists()
    assert not (dados / "politicos" / "2").exists()
    eleitos = json.loads((dados / "eleitos" / "m-3550308.json").read_text())
    assert [p["nome"] for p in site.expandir(eleitos)] == ["Vereadora 2024"]
    assert [
        p["id"]
        for p in site.expandir(json.loads((dados / "eleitos" / "uf-SP-2026.json").read_text()))
    ] == [3]
    # a página do município liga o eleito ao arquivo dele
    arquivo = json.loads((dados / "municipios" / "3550308.json").read_text())
    citados = [p for sec in _secoes(dados, arquivo) for g in sec["grupos"] for p in g["politicos"]]
    assert {"id": 2, "nome": "Vereadora 2024", "partido": "X", "eleito": "m-3550308"} in citados
    assert site.verificar(dados) == []


# --- formato 3: páginas, catálogos, cota, fontes por hash e exportação incremental ------

HOJE = date(2026, 10, 6)
URL_VOTOS = "https://exemplo.gov.br/votacoes/{}/votos"


def _resposta(banco, conteudo: bytes, url: str) -> RespostaBruta:
    sha = hashlib.sha256(conteudo).hexdigest()
    if banco.get(PayloadBruto, sha) is None:
        banco.add(
            PayloadBruto(
                sha256=sha, tamanho=len(conteudo), compressao="gzip",
                conteudo=gzip.compress(conteudo),
            )
        )  # fmt: skip
    r = RespostaBruta(
        metodo="GET", url=url, status_http=200, recebido_em=datetime.now(UTC),
        sha256=sha, tamanho=len(conteudo),
    )  # fmt: skip
    banco.add(r)
    banco.flush()
    return r


@pytest.fixture
def com_listas(com_politicos):
    """Dois deputados com 1.201 votos nas mesmas votações (mais de 2 páginas de 500)."""
    banco = com_politicos
    banco.add(
        _politico(
            id=4, fonte="camara", id_fonte="4", nome="Outro Dep", cargo="deputado_federal",
            em_exercicio=True,
        )
    )  # fmt: skip
    votos = _resposta(banco, b"votos-2025", "https://exemplo.gov.br/votacoes-2025.json")
    cota = _resposta(banco, b"cota-2025", "https://exemplo.gov.br/cota-2025.zip")
    for pid in (1, 4):
        banco.add_all(
            PolVotacao(
                politico_id=pid, id_votacao=f"V{i:04d}", data=date(2025, 1 + i % 12, 1 + i % 28),
                voto="Sim" if (i + pid) % 2 else "Não", orgao="PLEN", materia=f"PL {i}/2025",
                descricao="Votação de teste", url_fonte=URL_VOTOS.format(i),
                resposta_id=votos.id,
            )
            for i in range(1201)
        )  # fmt: skip
    banco.add_all(
        PolPresenca(
            politico_id=1, id_evento=str(e), data_hora_inicio=datetime(2025, 3, e, 10),
            url_fonte=f"https://exemplo.gov.br/eventos/{e}", resposta_id=votos.id,
        )
        for e in (1, 2, 3)
    )  # fmt: skip
    for ano, linhas in ((2025, 3), (2024, 2)):
        banco.add_all(
            PolDespesaCota(
                politico_id=1, ano=ano, mes=1, linha=n, categoria="TELEFONIA",
                valor_liquido=Decimal("10.50"), url_fonte="https://exemplo.gov.br/cota.zip",
                resposta_id=cota.id,
            )
            for n in range(linhas)
        )  # fmt: skip
    banco.commit()
    return banco


def _lista(dados: Path, pid: int, lista: str, ano: int) -> list[dict]:
    itens, n = [], 1
    while (arq := dados / "politicos" / str(pid) / lista / f"{ano}-{n}.json").exists():
        itens += site.expandir(json.loads(arq.read_text()))
        n += 1
    return itens


def test_lista_longa_nao_e_cortada_e_usa_catalogo(com_listas, tmp_path):
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", com_listas, hoje=HOJE)
    base = dados / "politicos" / "1" / "votacoes"
    assert sorted(p.name for p in base.iterdir()) == ["2025-1.json", "2025-2.json", "2025-3.json"]
    assert [len(json.loads((base / f"2025-{n}.json").read_text())["itens"]) for n in (1, 2, 3)] == [
        500, 500, 201,
    ]  # fmt: skip
    # sem "todos": o site junta os anos
    assert not list((dados / "politicos").glob("*/*/todos.json"))

    catalogo = {
        x["id_votacao"]: x
        for x in site.expandir(
            json.loads((dados / "catalogos" / "votacoes" / "camara" / "2025.json").read_text())
        )
    }
    assert len(catalogo) == 1201
    votos = _lista(dados, 1, "votacoes", 2025)
    # no arquivo do político ficam só o id e o voto; o resto vem do catálogo
    assert set().union(*(v.keys() for v in votos)) == {"id_votacao", "voto", "voto_descricao"}
    completos = [{**catalogo[v["id_votacao"]], **v} for v in votos]

    app.dependency_overrides[get_session] = lambda: com_listas
    try:
        api = TestClient(app)
        esperado = []
        for desloc in (0, 500, 1000):
            esperado += api.get(
                f"/api/politicos/1/votacoes?ano=2025&limite=500&deslocamento={desloc}"
            ).json()["itens"]
    finally:
        app.dependency_overrides.clear()
    assert len(completos) == len(esperado) == 1201
    sha = hashlib.sha256(b"votos-2025").hexdigest()
    for a, b in zip(completos, esperado, strict=True):
        assert a["sha256"] == sha and "resposta_id" not in a
        assert a == {**{k: v for k, v in b.items() if k != "resposta_id"}, "sha256": sha}

    presencas = _lista(dados, 1, "presencas", 2025)
    assert [p["id_evento"] for p in presencas] == ["3", "2", "1"]
    assert site.verificar(dados) == []


def test_lista_cortada_bloqueia_publicacao(com_listas, tmp_path):
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", com_listas, hoje=HOJE)
    (dados / "politicos" / "1" / "votacoes" / "2025-3.json").unlink()
    assert any(
        "politicos/1/votacoes/2025: 1000 itens nos arquivos, 1201 no detalhe" in p
        for p in site.verificar(dados)
    )


def test_cota_item_a_item_so_no_ano_corrente_e_no_anterior(com_listas, tmp_path):
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", com_listas, hoje=HOJE)
    base = dados / "politicos" / "1" / "cota"
    cab_2025 = json.loads((base / "2025.json").read_text())
    assert cab_2025["detalhada"] and cab_2025["paginas"] == 1 and cab_2025["aviso"] is None
    pagina = json.loads((base / "2025-1.json").read_text())
    # campos repetidos (categoria, fonte) vão para o cabeçalho
    assert pagina["comum"]["categoria"] == "TELEFONIA"
    assert pagina["comum"]["sha256"] == hashlib.sha256(b"cota-2025").hexdigest()
    assert len(site.expandir(pagina)) == 3

    cab_2024 = json.loads((base / "2024.json").read_text())
    assert cab_2024["detalhada"] is False and cab_2024["paginas"] == 0
    assert cab_2024["aviso"] == "Lançamentos detalhados disponíveis na página oficial da Câmara"
    assert cab_2024["url_oficial"] == (
        "https://www.camara.leg.br/transparencia/gastos-parlamentares?legislatura=57&ano=2024"
        "&mes=&por=deputado&deputado=1&uf=&partido="
    )
    assert cab_2024["por_categoria"] == [
        {"categoria": "TELEFONIA", "quantidade": 2, "valor_liquido": "21.00"}
    ]
    assert not (base / "2024-1.json").exists()
    assert site.verificar(dados) == []


def test_legislatura_do_ano():
    assert [site.legislatura(a) for a in (2019, 2022, 2023, 2026, 2027)] == [56, 56, 57, 57, 58]


def test_nenhum_arquivo_tem_id_interno_de_resposta(com_listas, tmp_path):
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", com_listas, hoje=HOJE)
    for arq in dados.rglob("*.json"):
        assert "resposta_id" not in arq.read_text(), arq
        assert "atualizado_em" not in arq.read_text(), arq


def test_exportacao_incremental(com_listas, tmp_path):
    dados = tmp_path / "dados"
    primeira = site.exportar(dados, "SP", com_listas, hoje=HOJE)["exportacao"]
    assert primeira["escritos"] == primeira["arquivos"]

    # nada mudou: todos os grupos reaproveitados; só o manifesto (data da exportação) muda
    segunda = site.exportar(dados, "SP", com_listas, hoje=HOJE)["exportacao"]
    assert segunda["grupos_reaproveitados"] == segunda["grupos"] > 0
    assert segunda["escritos"] == 1 and segunda["arquivos"] == primeira["arquivos"]
    assert site.verificar(dados) == []

    # um voto muda: o político, o outro que votou na mesma sessão não
    v = com_listas.scalar(PolVotacao.__table__.select().where(PolVotacao.politico_id == 4).limit(1))
    com_listas.get(PolVotacao, v).voto = "Abstenção"
    com_listas.commit()
    terceira = site.exportar(dados, "SP", com_listas, hoje=HOJE)["exportacao"]
    assert terceira["grupos_reaproveitados"] == terceira["grupos"] - 1
    assert 1 < terceira["escritos"] <= 5
    indice = json.loads((dados / "indice.json").read_text())

    # o resultado é igual ao de uma exportação completa do zero
    outra = tmp_path / "outra"
    site.exportar(outra, "SP", com_listas, hoje=HOJE, completa=True)
    outro = json.loads((outra / "indice.json").read_text())
    tirar = {"manifesto.json"}
    assert {k: v for k, v in indice["arquivos"].items() if k not in tirar} == {
        k: v for k, v in outro["arquivos"].items() if k not in tirar
    }
    assert site.verificar(dados) == []


def test_arquivo_reaproveitado_alterado_e_regravado(com_listas, tmp_path):
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", com_listas, hoje=HOJE)
    alvo = dados / "politicos" / "1" / "votacoes" / "2025-2.json"
    original = alvo.read_bytes()
    alvo.write_text('{"itens": []}')
    assert any("diferentes do índice" in p for p in site.verificar(dados))
    site.exportar(dados, "SP", com_listas, hoje=HOJE)
    assert alvo.read_bytes() == original
    assert site.verificar(dados) == []


def test_mudanca_de_ano_remove_lancamentos_antigos(com_listas, tmp_path):
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", com_listas, hoje=HOJE)
    assert (dados / "politicos" / "1" / "cota" / "2025-1.json").exists()
    e = site.exportar(dados, "SP", com_listas, hoje=date(2027, 1, 2))["exportacao"]
    # em 2027 os detalhados são 2027 e 2026: as páginas de 2025 saem do site
    assert not (dados / "politicos" / "1" / "cota" / "2025-1.json").exists()
    assert json.loads((dados / "politicos" / "1" / "cota" / "2025.json").read_text())["aviso"]
    assert e["removidos"] >= 1
    assert site.verificar(dados) == []
