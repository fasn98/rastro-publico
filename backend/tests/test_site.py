"""Site estático: exportação, verificação antes de publicar, publicação e reversão.

Os políticos vêm dos coletores reais, com as respostas das fontes gravadas em
tests/fixtures/politicos (nenhum dado inventado).
"""

import csv
import io
import json
import shutil
import subprocess
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from conftest import FIXTURES, carregar
from rastro import publicacao, site
from rastro.api.main import app
from rastro.coletores import ibge
from rastro.coletores.arquivo import ArquivoBruto
from rastro.coletores.base import executar, novo_cliente
from rastro.db import get_session
from rastro.models import Coleta, Municipio
from rastro.politicos import camara, transparencia, tse
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


# --- políticos a partir das respostas reais gravadas em tests/fixtures/politicos -----------

POL = FIXTURES / "politicos"
TABATA = 204534  # Tabata Amaral: proposições e uma emenda de 2024 nas amostras
JONAS = 160548  # Jonas Donizette: 928 lançamentos de cota em 2025 (mais de uma página)
HOJE = date(2026, 10, 6)  # data da exportação: cota item a item em 2026 e 2025


def _zip_cota() -> bytes:
    """Arquivo anual da cota (Ano-2025.csv.zip) no layout oficial, com as linhas do 160548.

    A fixture camara_cota_2025_SP_160548.csv foi extraída do Ano-2025.csv oficial em
    07/10/2026, já sem as colunas pessoais e com lgpd.apagar_pessoa_fisica aplicada. Aqui
    essas colunas voltam vazias só para reproduzir o layout que o coletor exige: nenhum
    valor é inventado e os originais não estão no repositório.
    """
    from test_cota_emendas import CABECALHO_COTA

    texto = (POL / "camara_cota_2025_SP_160548.csv").read_text()
    saida = io.StringIO()
    w = csv.DictWriter(saida, CABECALHO_COTA, delimiter=";", quoting=csv.QUOTE_ALL, restval="")
    w.writeheader()
    w.writerows(csv.DictReader(io.StringIO(texto), delimiter=";"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Ano-2025.csv", saida.getvalue().encode("utf-8-sig"))
    return buf.getvalue()


def _mapa(banco) -> dict[int, int]:
    """id da Câmara -> pol_politico.id"""
    return {
        int(i): pid
        for i, pid in banco.execute(
            select(PolPolitico.id_fonte, PolPolitico.id).where(PolPolitico.fonte == "camara")
        )
    }


def _ids(banco, *condicoes) -> set[int]:
    return set(banco.scalars(select(PolPolitico.id).where(*condicoes)))


@pytest.fixture
def coletado(banco, engine):
    """Banco montado pelos coletores reais, com as respostas gravadas das fontes:

    - Câmara: deputados de SP da legislatura 57, proposições de 2025 da Tabata Amaral,
      votos de 3 votações de 2025 e a cota de 2025 do deputado 160548;
    - Portal da Transparência: amostra do arquivo de emendas (a de 2024 da Tabata Amaral
      tem vínculo confirmado pelo nome, como em test_cota_emendas);
    - TSE: eleitos de 2024 da amostra de SP (com o cruzamento oficial TSE↔IBGE) e de 2026.
    As presenças ficam de fora: chegam depois, no teste da exportação incremental.
    """
    from test_cota_emendas import _zip_emendas
    from test_politicos import _mock_camara
    from test_tse import AMOSTRA_IBGE, _zip_original
    from test_tse import _mock as _mock_tse

    from rastro.politicos.vinculo import Autor

    with respx.mock:
        _mock_camara()
        _mock_tse()
        respx.get(tse.URL_CANDIDATOS.format(ano=2026)).respond(content=_zip_original(2026))
        respx.get(camara.URL_COTA.format(ano=2025)).respond(content=_zip_cota())
        respx.get(transparencia.URL_ARQUIVO).respond(content=_zip_emendas())
        with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
            mapa = camara.coletar_deputados(banco, c, "SP")
            camara.coletar_proposicoes(banco, c, TABATA, mapa[TABATA], 2025)
            camara.coletar_votos(banco, c, 2025, mapa)
            camara.coletar_cota(banco, c, 2025, "SP", mapa)
            autores = {
                transparencia.normalizar_nome("Tabata Amaral"): Autor(
                    mapa[TABATA], "Tabata Amaral", 2024, 2027
                )
            }
            executar(
                banco,
                "pol-emendas",
                lambda s, cl: transparencia.coletar_arquivo(s, cl, "SP", 2023, autores)["linhas"],
                c,
            )
            tse.coletar_eleitos(banco, c, 2024, "SP", AMOSTRA_IBGE)
            tse.coletar_eleitos(banco, c, 2026, "SP", set())
    return banco


def _coletar_presencas(banco, engine) -> set[int]:
    """Presenças de 2025 (amostra real do arquivo da Câmara); devolve quem ganhou presença."""
    from test_politicos import _mock_camara

    with respx.mock:
        _mock_camara()
        with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
            camara.coletar_presencas(banco, c, 2025, _mapa(banco))
    return set(banco.scalars(select(PolPresenca.politico_id).distinct()))


def test_coleta_real_tem_o_que_os_testes_usam(coletado):
    """Confere a premissa dos testes abaixo nas próprias fixtures (sem números inventados)."""
    mapa = _mapa(coletado)
    cota = coletado.scalar(select(func.count()).where(PolDespesaCota.politico_id == mapa[JONAS]))
    linhas = sum(1 for _ in csv.DictReader(
        io.StringIO((POL / "camara_cota_2025_SP_160548.csv").read_text()), delimiter=";"
    ))  # fmt: skip
    assert cota == linhas > site.TAM_PAGINA
    assert _ids(coletado, PolPolitico.fonte == "tse", PolPolitico.eleicao_ano == 2024)
    assert _ids(coletado, PolPolitico.fonte == "tse", PolPolitico.eleicao_ano == 2026)
    assert coletado.scalar(select(func.count()).where(PolEmenda.politico_id == mapa[TABATA]))


@pytest.mark.parametrize(
    ("tse_", "tse_2026", "emendas"), [("0", "0", "0"), ("1", "0", "0"), ("1", "1", "1")]
)
def test_travas_desligadas_nao_vao_para_o_site(
    coletado, tmp_path, monkeypatch, tse_, tse_2026, emendas
):
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE", tse_)
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE_2026", tse_2026)
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_EMENDAS", emendas)
    federais = _ids(coletado, PolPolitico.fonte != "tse")
    tse_2024 = _ids(coletado, PolPolitico.fonte == "tse", PolPolitico.eleicao_ano == 2024)
    tse_26 = _ids(coletado, PolPolitico.fonte == "tse", PolPolitico.eleicao_ano == 2026)
    esperados = (
        federais | (tse_2024 if tse_ == "1" else set()) | (tse_26 if tse_2026 == "1" else set())
    )
    dados = tmp_path / "dados"
    manifesto = site.exportar(dados, "SP", coletado, hoje=HOJE)
    exportados = {int(p.stem) for p in (dados / "politicos").glob("*.json")} | set(_eleitos(dados))
    assert exportados == esperados
    assert manifesto["travas"] == {
        "pol_publicar_tse": tse_ == "1",
        "pol_publicar_tse_2026": tse_2026 == "1",
        "pol_publicar_emendas": emendas == "1",
        "pol_publicar_gestoes": False,  # padrão (ADR-0018): desligada até a aprovação
    }
    texto = "".join(p.read_text() for p in dados.rglob("*.json"))
    vereador = coletado.get(PolPolitico, min(tse_2024))
    governador = coletado.get(PolPolitico, min(tse_26))
    assert (json.dumps(vereador.nome, ensure_ascii=False) in texto) == (tse_ == "1")
    assert (json.dumps(governador.nome, ensure_ascii=False) in texto) == (tse_2026 == "1")
    municipio = json.loads((dados / "municipios" / "3550308.json").read_text())
    assert municipio["emendas"]["publicadas"] == (emendas == "1")
    tabata = _mapa(coletado)[TABATA]
    detalhe = json.loads((dados / "politicos" / f"{tabata}.json").read_text())
    assert detalhe["emendas"]["publicadas"] == (emendas == "1")
    assert detalhe["emendas"]["anos"] == ([2024] if emendas == "1" else [])
    assert (dados / "politicos" / str(tabata) / "emendas" / "2024.json").exists() == (
        emendas == "1"
    )
    # todo político citado nas páginas dos municípios tem página própria
    assert site.verificar(dados) == []


def test_verificacao_recusa_dado_travado_no_arquivo(coletado, tmp_path, monkeypatch):
    """Segunda barreira: mesmo que algo travado escape da API, a publicação é recusada."""
    liberado = tmp_path / "liberado"
    site.exportar(liberado, "SP", coletado, hoje=HOJE)
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE", "0")
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE_2026", "0")
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_EMENDAS", "0")
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", coletado, hoje=HOJE)
    # arquivos reais da exportação com as travas ligadas, copiados para a travada
    tabata = _mapa(coletado)[TABATA]
    for caminho in ("eleitos/uf-SP-2026.json", f"politicos/{tabata}/emendas/2024.json"):
        (dados / caminho).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(liberado / caminho, dados / caminho)
    problemas = site.verificar(dados)
    assert any("uf-SP-2026.json" in p and "pol_publicar_tse_2026" in p for p in problemas)
    assert any(f"politicos/{tabata}/emendas/2024.json" in p for p in problemas)
    assert any("fora do índice" in p for p in problemas)


def test_verificacao_recusa_politico_citado_sem_pagina(coletado, tmp_path):
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", coletado, hoje=HOJE)
    (dados / "politicos" / f"{_mapa(coletado)[TABATA]}.json").unlink()
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


def test_simulacao_verifica_e_nao_envia_nada(exportado, remoto):
    dist, _ = exportado
    publicacao.publicar(dist, remoto, agora=datetime(2026, 10, 1, tzinfo=UTC))
    antes = _ramo(remoto)
    tag = publicacao.publicar(dist, remoto, agora=datetime(2026, 10, 2, tzinfo=UTC), simular=True)
    assert tag == "site-20261002-000000"
    assert _ramo(remoto) == antes
    assert [p["tag"] for p in publicacao.listar(remoto)] == ["site-20261001-000000"]


def test_token_nunca_aparece_em_mensagens():
    token = "github_pat_SEGREDO123"
    with pytest.raises(publicacao.ErroPublicacao) as erro:
        publicacao.listar("https://127.0.0.1:9/repo-inexistente.git", token)
    assert token not in str(erro.value)
    assert "***" in str(erro.value) or "127.0.0.1" in str(erro.value)


def test_eleito_do_tse_so_tem_o_arquivo_de_detalhe(coletado, tmp_path):
    """Eleitos do TSE não têm listas (proposições, votos...): só o detalhe é exportado."""
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", coletado, hoje=HOJE)
    adamantina = coletado.scalars(
        select(PolPolitico).where(PolPolitico.fonte == "tse", PolPolitico.cod_ibge == 3500105)
    ).all()
    assert adamantina
    for p in adamantina:
        assert not (dados / "politicos" / f"{p.id}.json").exists()
        assert not (dados / "politicos" / str(p.id)).exists()
    eleitos = site.expandir(json.loads((dados / "eleitos" / "m-3500105.json").read_text()))
    assert sorted(p["id"] for p in eleitos) == sorted(p.id for p in adamantina)
    governador = _ids(coletado, PolPolitico.fonte == "tse", PolPolitico.eleicao_ano == 2026)
    uf_2026 = site.expandir(json.loads((dados / "eleitos" / "uf-SP-2026.json").read_text()))
    assert {p["id"] for p in uf_2026} == governador
    # a página do município liga o eleito ao arquivo dele
    arquivo = json.loads((dados / "municipios" / "3500105.json").read_text())
    citados = [p for sec in _secoes(dados, arquivo) for g in sec["grupos"] for p in g["politicos"]]
    p = adamantina[0]
    assert {"id": p.id, "nome": p.nome, "partido": p.partido, "eleito": "m-3500105"} in citados
    assert site.verificar(dados) == []


# --- formato 3: páginas, catálogos, cota, fontes por hash e exportação incremental ------


def _lista(dados: Path, pid: int, lista: str, ano: int) -> list[dict]:
    itens, n = [], 1
    while (arq := dados / "politicos" / str(pid) / lista / f"{ano}-{n}.json").exists():
        itens += site.expandir(json.loads(arq.read_text()))
        n += 1
    return itens


def _api_lista(banco, pid: int, lista: str, ano: int) -> list[dict]:
    """A lista inteira pela API, em páginas de 500, com a fonte trocada pelo SHA-256."""
    from rastro.models import RespostaBruta

    app.dependency_overrides[get_session] = lambda: banco
    try:
        api, itens, desloc = TestClient(app), [], 0
        while True:
            r = api.get(
                f"/api/politicos/{pid}/{lista}?ano={ano}&limite=500&deslocamento={desloc}"
            ).json()
            pagina = r["despesas"] if lista == "cota" else r
            itens += pagina["itens"]
            desloc += 500
            if desloc >= pagina["total"]:
                break
    finally:
        app.dependency_overrides.clear()
    shas = dict(banco.execute(select(RespostaBruta.id, RespostaBruta.sha256)).all())
    return [
        {**{k: v for k, v in x.items() if k != "resposta_id"}, "sha256": shas[x["resposta_id"]]}
        for x in itens
    ]


def test_lista_longa_nao_e_cortada(coletado, tmp_path):
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", coletado, hoje=HOJE)
    jonas = _mapa(coletado)[JONAS]
    base = dados / "politicos" / str(jonas) / "cota"
    paginas = sorted(p.name for p in base.glob("2025-*.json"))
    assert paginas == ["2025-1.json", "2025-2.json"]
    tamanhos = [len(json.loads((base / n).read_text())["itens"]) for n in paginas]
    esperado = _api_lista(coletado, jonas, "cota", 2025)
    assert tamanhos == [500, len(esperado) - 500]
    # sem "todos": o site junta os anos
    assert not list((dados / "politicos").glob("*/*/todos.json"))
    assert _lista(dados, jonas, "cota", 2025) == esperado
    assert site.verificar(dados) == []


def test_votos_usam_o_catalogo(coletado, tmp_path):
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", coletado, hoje=HOJE)
    catalogo = {
        x["id_votacao"]: x
        for x in site.expandir(
            json.loads((dados / "catalogos" / "votacoes" / "camara" / "2025.json").read_text())
        )
    }
    assert set(catalogo) == set(coletado.scalars(select(PolVotacao.id_votacao).distinct()))
    votaram = coletado.execute(
        select(PolVotacao.politico_id).group_by(PolVotacao.politico_id)
        .order_by(func.count().desc(), PolVotacao.politico_id).limit(1)
    ).scalar_one()  # fmt: skip
    votos = _lista(dados, votaram, "votacoes", 2025)
    # no arquivo do político ficam só o id e o voto; o resto vem do catálogo
    assert set().union(*(v.keys() for v in votos)) <= {"id_votacao", "voto", "voto_descricao"}
    completos = [{**catalogo[v["id_votacao"]], **v} for v in votos]
    assert completos == _api_lista(coletado, votaram, "votacoes", 2025)
    assert site.verificar(dados) == []


def test_lista_cortada_bloqueia_publicacao(coletado, tmp_path):
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", coletado, hoje=HOJE)
    jonas = _mapa(coletado)[JONAS]
    total = coletado.scalar(select(func.count()).where(PolDespesaCota.politico_id == jonas))
    (dados / "politicos" / str(jonas) / "cota" / "2025-2.json").unlink()
    assert any(
        f"politicos/{jonas}/cota/2025: 500 itens nos arquivos, {total} no detalhe" in p
        for p in site.verificar(dados)
    )


def _categorias_da_fixture() -> dict[str, tuple[int, Decimal]]:
    """Totais por categoria calculados direto do CSV da fixture, sem passar pelo coletor."""
    totais: dict[str, tuple[int, Decimal]] = {}
    texto = (POL / "camara_cota_2025_SP_160548.csv").read_text()
    for r in csv.DictReader(io.StringIO(texto), delimiter=";"):
        n, v = totais.get(r["txtDescricao"], (0, Decimal(0)))
        totais[r["txtDescricao"]] = (n + 1, v + Decimal(r["vlrLiquido"] or 0))
    return totais


def test_cota_item_a_item_so_no_ano_corrente_e_no_anterior(coletado, tmp_path):
    from rastro.models import RespostaBruta

    jonas = _mapa(coletado)[JONAS]
    dados = tmp_path / "dados"
    # exportação em 2026: 2025 é o ano anterior, com os lançamentos item a item
    site.exportar(dados, "SP", coletado, hoje=HOJE)
    base = dados / "politicos" / str(jonas) / "cota"
    cab = json.loads((base / "2025.json").read_text())
    assert cab["detalhada"] and cab["paginas"] == 2 and cab["aviso"] is None
    pagina = json.loads((base / "2025-1.json").read_text())
    # campos repetidos (fonte, categoria) vão para o cabeçalho
    sha_cota = coletado.scalar(
        select(RespostaBruta.sha256).where(RespostaBruta.url.like("%/cotas/Ano-2025%"))
    )
    assert pagina["comum"]["sha256"] == sha_cota
    assert "categoria" in pagina["indices"]
    esperado = {c: (n, v) for c, (n, v) in _categorias_da_fixture().items()}
    assert {
        x["categoria"]: (x["quantidade"], Decimal(x["valor_liquido"])) for x in cab["por_categoria"]
    } == esperado

    # a mesma base exportada em 2027: 2025 sai do item a item e fica só com os totais
    site.exportar(dados, "SP", coletado, hoje=date(2027, 1, 2))
    cab = json.loads((base / "2025.json").read_text())
    assert cab["detalhada"] is False and cab["paginas"] == 0
    assert cab["aviso"] == "Lançamentos detalhados disponíveis na página oficial da Câmara"
    assert cab["url_oficial"] == (
        "https://www.camara.leg.br/transparencia/gastos-parlamentares?legislatura=57&ano=2025"
        f"&mes=&por=deputado&deputado={JONAS}&uf=&partido="
    )
    assert {
        x["categoria"]: (x["quantidade"], Decimal(x["valor_liquido"])) for x in cab["por_categoria"]
    } == esperado
    assert not list(base.glob("2025-*.json"))
    assert site.verificar(dados) == []


def test_legislatura_do_ano():
    assert [site.legislatura(a) for a in (2019, 2022, 2023, 2026, 2027)] == [56, 56, 57, 57, 58]


def test_nenhum_arquivo_tem_id_interno_de_resposta(coletado, tmp_path):
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", coletado, hoje=HOJE)
    for arq in dados.rglob("*.json"):
        assert "resposta_id" not in arq.read_text(), arq
        assert "atualizado_em" not in arq.read_text(), arq


def test_exportacao_incremental(coletado, engine, tmp_path):
    dados = tmp_path / "dados"
    primeira = site.exportar(dados, "SP", coletado, hoje=HOJE)["exportacao"]
    assert primeira["escritos"] == primeira["arquivos"]

    # nada mudou: todos os grupos reaproveitados; só o manifesto (data da exportação) muda
    segunda = site.exportar(dados, "SP", coletado, hoje=HOJE)["exportacao"]
    assert segunda["grupos_reaproveitados"] == segunda["grupos"] > 0
    assert segunda["escritos"] == 1 and segunda["arquivos"] == primeira["arquivos"]
    assert site.verificar(dados) == []

    # chegam as presenças de 2025: só os deputados que ganharam presença são refeitos
    com_presenca = _coletar_presencas(coletado, engine)
    assert com_presenca
    terceira = site.exportar(dados, "SP", coletado, hoje=HOJE)["exportacao"]
    assert terceira["grupos_reaproveitados"] == terceira["grupos"] - len(com_presenca)
    indice = json.loads((dados / "indice.json").read_text())

    # o resultado é igual ao de uma exportação completa do zero
    outra = tmp_path / "outra"
    site.exportar(outra, "SP", coletado, hoje=HOJE, completa=True)
    outro = json.loads((outra / "indice.json").read_text())
    assert indice["arquivos"] == outro["arquivos"]
    assert site.verificar(dados) == []


def test_arquivo_reaproveitado_alterado_e_regravado(coletado, tmp_path):
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", coletado, hoje=HOJE)
    base = dados / "politicos" / str(_mapa(coletado)[JONAS]) / "cota"
    alvo = base / "2025-2.json"
    original = alvo.read_bytes()
    shutil.copy(base / "2025-1.json", alvo)  # conteúdo real, no lugar errado
    assert any("diferentes do índice" in p for p in site.verificar(dados))
    site.exportar(dados, "SP", coletado, hoje=HOJE)
    assert alvo.read_bytes() == original
    assert site.verificar(dados) == []


def test_previa_sem_ranking_nao_exporta_ranking_nem_notas(banco, tmp_path):
    dados = tmp_path / "dados"
    manifesto = site.exportar(dados, "SP", banco, sem_ranking=True)
    assert not (dados / "ranking.json").exists() and not (dados / "ranking.csv").exists()
    for arq in (dados / "municipios").glob("*.json"):
        assert json.loads(arq.read_text())["nota"] is None
    assert manifesto["contagens"]["municipios_com_nota"] == 0
    assert site.verificar(dados) == []


# --- exportação incremental a partir do que está publicado (coleta agendada) ---------------


def test_baixar_publicado_sem_publicacao(remoto, tmp_path):
    destino = tmp_path / "base"
    assert publicacao.baixar_publicado(remoto, destino) is None
    assert destino.is_dir() and not any(destino.iterdir())


def test_baixar_publicado_recusa_pasta_com_arquivos(remoto, tmp_path):
    destino = tmp_path / "base"
    destino.mkdir()
    (destino / "velho.json").write_text("{}")
    with pytest.raises(publicacao.ErroPublicacao, match="não está vazia"):
        publicacao.baixar_publicado(remoto, destino)


def test_coleta_parte_do_publicado_e_reaproveita(coletado, remoto, tmp_path):
    # 1ª coleta: exporta do zero e publica (frontend compilado + dados/)
    dist = tmp_path / "dist"
    site.exportar(dist / "dados", "SP", coletado, hoje=HOJE)
    (dist / "index.html").write_text("<!doctype html><title>Rastro</title>")
    publicacao.publicar(dist, remoto, agora=datetime(2026, 10, 1, tzinfo=UTC))

    # 2ª coleta, noutra máquina (pasta vazia): baixa o dados/ publicado e exporta por cima
    base = tmp_path / "site-dados"
    manifesto = publicacao.baixar_publicado(remoto, base)
    assert manifesto is not None and (base / "indice.json").exists()
    assert not (base / "index.html").exists() and not (base / ".nojekyll").exists()
    assert site.verificar(base) == []
    exp = site.exportar(base, "SP", coletado, hoje=HOJE)["exportacao"]
    # nada mudou na fonte: todos os grupos reaproveitados, só o manifesto regravado
    assert exp["grupos_reaproveitados"] == exp["grupos"] > 0
    assert exp["escritos"] == 1
    assert site.verificar(base) == []


# --- falha de uma fonte não impede a publicação das demais -------------------------------


def _sem_camara(banco) -> int:
    """Banco como o de uma produção nova em que a Câmara nunca respondeu."""
    from sqlalchemy import text

    ids = list(_ids(banco, PolPolitico.fonte == "camara"))
    for tabela in (
        "pol_comissao", "pol_presenca", "pol_proposicao", "pol_votacao",
        "pol_despesa_cota", "pol_evento_mandato",
    ):  # fmt: skip
        banco.execute(text(f"DELETE FROM {tabela} WHERE politico_id = ANY(:ids)"), {"ids": ids})
    banco.execute(
        text("UPDATE pol_emenda SET politico_id = NULL WHERE politico_id = ANY(:ids)"), {"ids": ids}
    )
    banco.execute(text("DELETE FROM pol_politico WHERE id = ANY(:ids)"), {"ids": ids})
    banco.commit()
    return len(ids)


def _camara_fora_do_ar(banco, monkeypatch) -> object:
    """A coleta real da Câmara (`rastro politicos`) com a API respondendo 504 sempre."""
    from rastro import fontes
    from rastro.politicos.coletar import coletor_camara

    monkeypatch.setenv("RASTRO_HTTP_TENTATIVAS", "1")
    from rastro.config import get_settings

    get_settings.cache_clear()
    with respx.mock:
        respx.get(url__startswith=f"{camara.API}/deputados").respond(504)
        coleta = fontes.executar_com_esperas(
            banco,
            "pol-camara",
            coletor_camara("SP", [2025]),
            lambda: novo_cliente(req_por_segundo=0, arquivo=False),
            esperas=[60, 120],
            dormir=lambda s: None,
        )
    get_settings.cache_clear()
    return coleta


def test_fonte_sem_dado_anterior_falha_e_o_site_e_publicado_com_aviso(
    coletado, remoto, tmp_path, monkeypatch
):
    from rastro import fontes

    # publicação anterior (como a prévia), com os deputados da Câmara
    dist = tmp_path / "dist"
    anterior = site.exportar(dist / "dados", "SP", coletado, hoje=HOJE)
    (dist / "index.html").write_text("<!doctype html><title>Rastro</title>")
    publicacao.publicar(dist, remoto, agora=datetime(2026, 10, 7, tzinfo=UTC))
    no_ar = _ramo(remoto)

    # produção nova: a Câmara nunca respondeu e responde 504 nesta coleta também
    deputados = _sem_camara(coletado)
    assert deputados > 0
    inicio = datetime.now(UTC)
    monkeypatch.setenv("RASTRO_INICIO_COLETA", inicio.isoformat())
    coleta = _camara_fora_do_ar(coletado, monkeypatch)
    assert coleta.status == "falha" and coleta.erro.startswith("HTTP 504 após 3 tentativas")

    situacao = fontes.status(coletado, inicio)
    assert fontes.resumo(situacao) == (
        "Fontes com falha: pol-camara (HTTP 504 após 3 tentativas; sem dado anterior: "
        "fonte indisponível nesta coleta)"
    )

    # a coleta segue: baixa o publicado, exporta e publica (sem recusar)
    nova = tmp_path / "dist2"
    publicacao.baixar_publicado(remoto, nova / "dados")
    manifesto = site.exportar(nova / "dados", "SP", coletado, hoje=HOJE)
    assert manifesto["contagens"]["politicos"] < anterior["contagens"]["politicos"]
    camara_ = next(f for f in manifesto["fontes"] if f["fonte"] == "pol-camara")
    assert camara_ == {
        "fonte": "pol-camara",
        "nome": "Câmara dos Deputados",
        "ultima_atualizacao": None,
        "tentada_nesta_coleta": True,
        "atualizada_nesta_coleta": False,
        "disponivel": False,
        "falha": "HTTP 504 após 3 tentativas",
    }
    assert site.verificar(nova / "dados", anterior) == []
    (nova / "index.html").write_text("<!doctype html><title>Rastro</title>")
    publicacao.publicar(nova, remoto, agora=datetime(2026, 10, 8, 4, 50, tzinfo=UTC))
    assert _ramo(remoto) != no_ar  # publicado


def test_fonte_com_dado_anterior_falha_e_o_site_sai_com_os_dados_anteriores(
    coletado, tmp_path, monkeypatch
):
    anterior = site.exportar(tmp_path / "antes", "SP", coletado, hoje=HOJE)
    # a Câmara já tinha sido coletada com sucesso numa execução anterior
    coletado.add(
        Coleta(
            fonte="pol-camara",
            status="sucesso",
            iniciada_em=datetime(2026, 10, 1, 4, 20, tzinfo=UTC),
            finalizada_em=datetime(2026, 10, 1, 5, 0, tzinfo=UTC),
        )
    )
    coletado.commit()
    monkeypatch.setenv("RASTRO_INICIO_COLETA", datetime.now(UTC).isoformat())
    assert _camara_fora_do_ar(coletado, monkeypatch).status == "falha"

    manifesto = site.exportar(tmp_path / "depois", "SP", coletado, hoje=HOJE)
    # os deputados continuam no banco e no site
    assert manifesto["contagens"]["politicos"] == anterior["contagens"]["politicos"]
    camara_ = next(f for f in manifesto["fontes"] if f["fonte"] == "pol-camara")
    assert camara_["disponivel"] and not camara_["atualizada_nesta_coleta"]
    assert camara_["ultima_atualizacao"].startswith("2026-10-01")
    assert site.verificar(tmp_path / "depois", anterior) == []


def test_queda_de_politicos_sem_fonte_indisponivel_continua_bloqueando(coletado, tmp_path):
    dados = tmp_path / "dados"
    manifesto = site.exportar(dados, "SP", coletado, hoje=HOJE)
    anterior = {**manifesto, "contagens": {**manifesto["contagens"], "politicos": 99999}}
    assert any("politicos:" in p for p in site.verificar(dados, anterior))
