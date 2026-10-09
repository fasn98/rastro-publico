"""Prefeitos eleitos em cada exercício (ADR-0018), com respostas reais do TSE.

As fixtures tse_consulta_cand_{2020,2024}_SP_prefeitos.csv são as linhas de prefeito e
vice-prefeito (cargos 11 e 12) de 10 municípios de SP nos arquivos consulta_cand_2020 e
consulta_cand_2024 do TSE (baixados em 09/10/2026), já SEM as colunas pessoais. Como em
test_tse, o teste remonta o layout original com marcadores nas colunas pessoais.

Os municípios cobrem os casos da regra: reeleito com nome de urna diferente (Campinas),
troca em 2025 (Adamantina), 2º turno (São Paulo), suplementar em 2022 depois de outra
anulada (Leme), em 2023 (Itupeva, Ubarana), em 2024 (Analândia) e em 2025 (Mongaguá),
mandato sem eleito (Sarutaiá) e suplementar ainda sem resultado (Macedônia).
"""

import csv
import gzip
import io
import zipfile

import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_indicadores_novos import COD, coletado, ente  # noqa: F401 (fixtures)
from test_ranking import populacao_ibge  # noqa: F401 (fixture)
from test_tse import CABECALHO, _marcador, _trava, _zip_municipios

from conftest import FIXTURES, carregar
from rastro import ranking as rk
from rastro.api.main import app
from rastro.coletores import ibge
from rastro.coletores.arquivo import ArquivoBruto
from rastro.coletores.base import novo_cliente
from rastro.db import get_session
from rastro.models import Municipio, PayloadBruto
from rastro.politicos import gestoes, tse
from rastro.politicos.modelos import PolEleicaoPrefeito

POL = FIXTURES / "politicos"
JANELA = [2023, 2024, 2025]


def _linhas(ano: int) -> list[dict]:
    texto = (POL / f"tse_consulta_cand_{ano}_SP_prefeitos.csv").read_text()
    return list(csv.DictReader(io.StringIO(texto), delimiter=";"))


def _zip(ano: int, linhas: list[dict] | None = None) -> bytes:
    saida = io.StringIO()
    w = csv.DictWriter(
        saida, CABECALHO, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n"
    )
    w.writeheader()
    for i, r in enumerate(linhas if linhas is not None else _linhas(ano)):
        w.writerow({**r, **{c: _marcador(c, i) for c in tse.COLUNAS_PESSOAIS}})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"consulta_cand_{ano}_SP.csv", saida.getvalue().encode("latin-1"))
    return buf.getvalue()


def _codigos() -> dict[str, int]:
    """Nome do município no arquivo do TSE (NM_UE) -> código IBGE, pela tabela oficial
    TSE <-> IBGE gravada (ligação pelo código TSE, SG_UE)."""
    nomes = {r["SG_UE"]: r["NM_UE"] for r in _linhas(2020)}
    texto = (POL / "tse_municipio_tse_ibge_SP.csv").read_text()
    return {
        nomes[r["CD_MUNICIPIO_TSE"]]: int(r["CD_MUNICIPIO_IBGE"])
        for r in csv.DictReader(io.StringIO(texto), delimiter=";")
        if r["CD_MUNICIPIO_TSE"] in nomes
    }


@pytest.fixture
def cliente(engine):
    with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
        yield c


def _coletar(session, cliente, zips: dict[int, bytes] | None = None) -> dict[int, dict]:
    zips = zips or {}
    codigos = set(_codigos().values())
    with respx.mock:
        respx.get(tse.URL_MUNICIPIOS).respond(content=_zip_municipios())
        for ano in gestoes.MANDATOS:
            respx.get(tse.URL_CANDIDATOS.format(ano=ano)).respond(content=zips.get(ano, _zip(ano)))
        return {
            ano: gestoes.coletar(session, cliente, ano, "SP", codigos) for ano in gestoes.MANDATOS
        }


@pytest.fixture
def coletados(session, cliente):
    _coletar(session, cliente)
    return session


def _resumo(session, nome: str) -> str | None:
    eleicoes = gestoes.eleicoes_do_municipio(session, _codigos()[nome])
    return gestoes.resumo_do_periodo(gestoes.mandatos(eleicoes), JANELA)


def test_fixtures_tem_os_10_municipios_e_casam_com_a_tabela_oficial():
    assert len(_codigos()) == 10
    for ano in (2020, 2024):
        assert {r["CD_CARGO"] for r in _linhas(ano)} == {"11", "12"}
        assert not set(tse.COLUNAS_PESSOAIS) & set(_linhas(ano)[0])


def test_coleta_grava_todas_as_eleicoes_sem_dados_pessoais(session, cliente):
    resumo = _coletar(session, cliente)
    for ano, r in resumo.items():
        linhas = _linhas(ano)
        eleicoes = {(x["SG_UE"], x["CD_ELEICAO"]) for x in linhas}
        com_eleito = {
            (x["SG_UE"], x["CD_ELEICAO"])
            for x in linhas
            if x["CD_CARGO"] == "11" and x["DS_SIT_TOT_TURNO"] == "ELEITO"
        }
        assert r == {"eleicoes": len(eleicoes), "com_eleito": len(com_eleito), "municipios": 10}
    # nenhum marcador das colunas pessoais na tabela nem no arquivo bruto
    linhas = [str(e.__dict__) for e in session.scalars(select(PolEleicaoPrefeito))]
    brutos = [gzip.decompress(p.conteudo) for p in session.scalars(select(PayloadBruto))]
    assert not any("MARCADOR" in x or "exemplo.invalid" in x for x in linhas)
    assert not any(b"MARCADOR" in b or b"exemplo.invalid" in b for b in brutos)


@pytest.mark.parametrize(
    ("municipio", "esperado"),
    [
        # 2º turno em 2020; o TSE registra o eleito, não quem exerceu o cargo
        ("SÃO PAULO", "2023–2024: BRUNO COVAS (PSDB), vice RICARDO NUNES (MDB); "
                      "2025: RICARDO NUNES (MDB), vice CORONEL MELLO ARAUJO (PL)"),
        # reeleito: dois mandatos, sem ligar a pessoa (o nome de urna muda)
        ("CAMPINAS", "2023–2024: DARIO SAADI (REPUBLICANOS), vice WANDÃO DE ALMEIDA (PSB); "
                     "2025: DÁRIO SAADI (REPUBLICANOS), vice WANDÃO ALMEIDA (PSB)"),
        ("ADAMANTINA", "2023–2024: MARCIO CARDIM (DEM), vice DINHA (DEM); "
                       "2025: JOSÉ TIVERON (NOVO), vice LÚCIA HAGA (PRD)"),
        # suplementar em dezembro de 2023: o eleito original cassado não é nomeado
        ("ITUPEVA", "2023–2024: sem eleito válido no arquivo atual do TSE; a eleição "
                    "suplementar de 03/12/2023 elegeu ROGÉRIO CAVALIN (MDB), vice ISAQUE "
                    "MESSIAS (MDB); 2025: ROGÉRIO CAVALIN (MDB), vice ISAQUE MESSIAS (UNIÃO)"),
        # suplementar em 2024: o ano anterior fica só sem eleito
        ("ANALÂNDIA", "2023: sem eleito válido no arquivo atual do TSE; 2024: sem eleito "
                      "válido no arquivo atual do TSE; a eleição suplementar de 07/04/2024 "
                      "elegeu SILVANA PERIN (SOLIDARIEDADE), vice VRÁ MASCIA (UNIÃO); "
                      "2025: SILVANA PERIN (SOLIDARIEDADE), vice VRA MASCIA (UNIÃO)"),
        # duas suplementares: vale a mais recente com eleito (a de 2021 foi anulada)
        ("LEME", "2023–2024: sem eleito válido no arquivo atual do TSE; a eleição "
                 "suplementar de 11/12/2022 elegeu CLAUDEMIR BORGES (PSD), vice CHICO DA "
                 "FARMACIA (PSD); 2025: CLAUDEMIR BORGES (PSD), vice RAUL NOGUEIRA - XUXU (MDB)"),
        ("MONGAGUÁ", "2023–2024: MÁRCIO CABEÇA (REPUBLICANOS), vice RAFAEL REDÓ (DEM); 2025: "
                     "sem eleito válido no arquivo atual do TSE; a eleição suplementar de "
                     "08/06/2025 elegeu CRISTINA (PP), vice JULIO (PDT)"),
        # sem eleito no mandato 2025–2028 (sem suplementar / suplementar sem resultado)
        ("SARUTAIÁ", "2023–2024: ISNAR (PTB), vice SERGIO FERRAZZI (SOLIDARIEDADE); "
                     "2025: sem eleito válido no arquivo atual do TSE"),
        ("MACEDÔNIA", "2023–2024: REGINALDO MARCOMINI (PSD), vice VANJA (PL); "
                      "2025: sem eleito válido no arquivo atual do TSE"),
        # partido da eleição, como no TSE (muda entre a suplementar e a ordinária)
        ("UBARANA", "2023–2024: sem eleito válido no arquivo atual do TSE; a eleição "
                    "suplementar de 03/12/2023 elegeu DELEI (SOLIDARIEDADE), vice NEI (PP); "
                    "2025: DELEI (PSD), vice NEI (PP)"),
    ],
)  # fmt: skip
def test_prefeitos_eleitos_no_periodo_da_nota(coletados, municipio, esperado):
    assert _resumo(coletados, municipio) == esperado


def test_mandato_nao_coletado_fica_sem_texto(session, cliente):
    """Sem o arquivo de 2024 no banco, a coluna não é montada pela metade."""
    with respx.mock:
        respx.get(tse.URL_MUNICIPIOS).respond(content=_zip_municipios())
        respx.get(tse.URL_CANDIDATOS.format(ano=2020)).respond(content=_zip(2020))
        gestoes.coletar(session, cliente, 2020, "SP", set(_codigos().values()))
    assert _resumo(session, "ADAMANTINA") is None
    eleicoes = gestoes.eleicoes_do_municipio(session, _codigos()["ADAMANTINA"])
    assert gestoes.resumo_do_periodo(gestoes.mandatos(eleicoes), [2023, 2024]) == (
        "2023–2024: MARCIO CARDIM (DEM), vice DINHA (DEM)"
    )


def test_chapa_sem_vice_eleito_falha_sem_gravar(session, cliente):
    """Prefeito eleito sem o vice da mesma chapa no arquivo: a coleta falha e nada é gravado."""
    linhas = [
        r for r in _linhas(2020)
        if not (r["NM_UE"] == "ADAMANTINA" and r["CD_CARGO"] == "12"
                and r["DS_SIT_TOT_TURNO"] == "ELEITO")
    ]  # fmt: skip
    with pytest.raises(gestoes.ColetaInvalida, match="ADAMANTINA"):
        _coletar(session, cliente, {2020: _zip(2020, linhas)})
    assert session.scalar(select(func.count()).select_from(PolEleicaoPrefeito)) == 0


@pytest.fixture
def api(coletados):
    coletados.add_all(Municipio(**ibge.normalizar(m)) for m in carregar("ibge_municipios.json"))
    coletados.commit()
    app.dependency_overrides[get_session] = lambda: coletados
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_com_a_trava_desligada_nao_mostra_nada(api, monkeypatch):
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_GESTOES", "0")
    r = api.get("/api/municipios/3550308/prefeitos").json()
    assert r["publicados"] is False and r["aviso"]
    assert r["mandatos"] == [] and r["exercicios"] == []


def test_api_mostra_mandatos_e_exercicios(api, monkeypatch):
    _trava(monkeypatch, "RASTRO_POL_PUBLICAR_GESTOES", "1")
    r = api.get("/api/municipios/3550308/prefeitos").json()
    assert r["publicados"] is True
    m2020, m2024 = r["mandatos"]
    assert (m2020["inicio"], m2020["fim"], m2020["situacao"]) == (2021, 2024, "ordinaria")
    e = m2020["eleicao"]
    assert (e["data"], e["turno"], e["suplementar"]) == ("2020-11-29", 2, False)
    assert e["prefeito"] == {"nome": "BRUNO COVAS", "partido": "PSDB"}
    assert e["vice"] == {"nome": "RICARDO NUNES", "partido": "MDB"}
    assert e["url_fonte"] == tse.URL_CANDIDATOS.format(ano=2020) and e["resposta_id"]
    assert m2024["eleicao"]["prefeito"] == {"nome": "RICARDO NUNES", "partido": "MDB"}
    anos = {x["ano"]: x for x in r["exercicios"]}
    assert sorted(anos) == list(range(2021, 2029))
    assert anos[2023]["texto"] == "BRUNO COVAS (PSDB), vice RICARDO NUNES (MDB)"
    assert anos[2025]["mandato"] == "2025–2028"


def test_ranking_traz_os_prefeitos_so_com_a_trava(
    coletados,
    coletado,  # noqa: F811
    populacao_ibge,  # noqa: F811
    monkeypatch,
):
    rk.calcular(coletados, "SP")
    app.dependency_overrides[get_session] = lambda: coletados
    try:
        api = TestClient(app)
        _trava(monkeypatch, "RASTRO_POL_PUBLICAR_GESTOES", "0")
        item = api.get("/api/ranking").json()["itens"][0]
        assert item["cod_ibge"] == COD and item["prefeitos_no_periodo"] is None
        cabecalho = api.get("/api/ranking.csv").content.decode("utf-8-sig").splitlines()[0]
        assert "prefeitos" not in cabecalho

        _trava(monkeypatch, "RASTRO_POL_PUBLICAR_GESTOES", "1")
        item = api.get("/api/ranking").json()["itens"][0]
        assert item["prefeitos_no_periodo"] == (
            "2023–2024: MARCIO CARDIM (DEM), vice DINHA (DEM); "
            "2025: JOSÉ TIVERON (NOVO), vice LÚCIA HAGA (PRD)"
        )
        texto = api.get("/api/ranking.csv").content.decode("utf-8-sig")
        linha = next(csv.DictReader(io.StringIO(texto), delimiter=";"))
        assert linha["prefeitos_eleitos_no_periodo"] == item["prefeitos_no_periodo"]
    finally:
        app.dependency_overrides.clear()
