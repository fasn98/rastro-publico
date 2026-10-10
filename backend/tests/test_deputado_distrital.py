"""DF: deputados distritais (cargo 8 do TSE), no lugar dos deputados estaduais.

As amostras tse_consulta_cand_{2022,2026}_DF_distritais.csv são linhas reais dos arquivos
consulta_cand_2022.zip e consulta_cand_2026.zip do TSE (baixados em 10/10/2026), já SEM as
colunas pessoais: todos os eleitos de deputado distrital do DF (24 em cada ano) e alguns
não eleitos. Como em test_tse.py, o teste remonta o ZIP no layout original, com MARCADORES
DE TESTE nas colunas pessoais.
"""

import csv
import io
import zipfile

import pytest
import respx
from sqlalchemy import func, select
from test_tse import CABECALHO, _marcador, _trava

from conftest import FIXTURES
from rastro.coletores.arquivo import ArquivoBruto
from rastro.coletores.base import novo_cliente
from rastro.politicos import tse
from rastro.politicos.modelos import (
    DEPUTADO_DISTRITAL,
    DEPUTADO_ESTADUAL,
    GOVERNADOR,
    PolPendencia,
    PolPolitico,
)

POL = FIXTURES / "politicos"
BRASILIA = 5300108


def _amostra(ano: int) -> list[dict]:
    texto = (POL / f"tse_consulta_cand_{ano}_DF_distritais.csv").read_text()
    return list(csv.DictReader(io.StringIO(texto), delimiter=";"))


def _zip_df(ano: int) -> bytes:
    saida = io.StringIO()
    w = csv.DictWriter(
        saida, CABECALHO, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n"
    )
    w.writeheader()
    for i, r in enumerate(_amostra(ano)):
        w.writerow({**r, **{c: _marcador(c, i) for c in tse.COLUNAS_PESSOAIS}})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"consulta_cand_{ano}_DF.csv", saida.getvalue().encode("latin-1"))
    return buf.getvalue()


def _eleitos(ano: int) -> set[str]:
    return {r["SQ_CANDIDATO"] for r in _amostra(ano) if r["DS_SIT_TOT_TURNO"] in tse.ELEITO}


@pytest.fixture
def cliente(engine):
    with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
        yield c


def test_amostras_sao_do_cargo_8_com_24_eleitos():
    for ano in (2022, 2026):
        linhas = _amostra(ano)
        assert {(r["SG_UF"], r["CD_CARGO"], r["DS_CARGO"]) for r in linhas} == {
            ("DF", "8", "DEPUTADO DISTRITAL")
        }
        assert len(_eleitos(ano)) == 24
        assert not set(linhas[0]) & set(tse.COLUNAS_PESSOAIS)


@pytest.mark.parametrize("ano", [2022, 2026])
@respx.mock
def test_df_grava_os_24_deputados_distritais(session, cliente, ano):
    respx.get(tse.URL_CANDIDATOS.format(ano=ano)).respond(content=_zip_df(ano))
    r = tse.coletar_eleitos(session, cliente, ano, "DF", set())
    assert r["eleitos"] == 24 and r["pendencias"] == 0
    distritais = session.scalars(
        select(PolPolitico).where(PolPolitico.cargo == DEPUTADO_DISTRITAL)
    ).all()
    assert {p.id_fonte for p in distritais} == _eleitos(ano)
    assert {(p.uf, p.cod_ibge, p.eleicao_ano, p.fonte) for p in distritais} == {
        ("DF", None, ano, "tse")
    }
    assert not any("MARCADOR-TESTE" in p.nome for p in distritais)
    assert (
        session.scalar(
            select(func.count())
            .select_from(PolPolitico)
            .where(PolPolitico.cargo == DEPUTADO_ESTADUAL)
        )
        == 0
    )
    assert session.scalar(select(func.count()).select_from(PolPendencia)) == 0


@respx.mock
def test_representantes_de_brasilia_mostram_os_distritais(session, cliente, monkeypatch):
    from fastapi.testclient import TestClient

    from rastro.api.main import app
    from rastro.db import get_session
    from rastro.models import Municipio

    session.add(Municipio(cod_ibge=BRASILIA, nome="Brasília", uf="DF", regiao="CO"))
    session.commit()
    respx.get(tse.URL_CANDIDATOS.format(ano=2022)).respond(content=_zip_df(2022))
    tse.coletar_eleitos(session, cliente, 2022, "DF", set())
    app.dependency_overrides[get_session] = lambda: session
    try:
        api = TestClient(app)
        _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE", "1")
        secoes = api.get(f"/api/municipios/{BRASILIA}/representantes").json()["secoes"]
        [estado] = [s for s in secoes if "Distrito Federal" in s["titulo"]]
        assert estado["titulo"].startswith("Governador e deputados distritais eleitos pelo DF")
        assert [g["cargo"] for g in estado["grupos"]] == [GOVERNADOR, DEPUTADO_DISTRITAL]
        [distritais] = [g for g in estado["grupos"] if g["cargo"] == DEPUTADO_DISTRITAL]
        assert len(distritais["politicos"]) == 24 and distritais["pendente"] is None
        assert not any(g["cargo"] == DEPUTADO_ESTADUAL for s in secoes for g in s["grupos"])
    finally:
        app.dependency_overrides.clear()


def test_fora_do_df_a_secao_estadual_continua_com_deputados_estaduais():
    from rastro.api.politicos import SECOES, _cargos_secao

    estado = dict(SECOES)["estado"]
    assert _cargos_secao("estado", estado, "SP") == (GOVERNADOR, DEPUTADO_ESTADUAL)
    assert _cargos_secao("estado", estado, "DF") == (GOVERNADOR, DEPUTADO_DISTRITAL)
    assert _cargos_secao("municipio", dict(SECOES)["municipio"], "DF") == dict(SECOES)["municipio"]
