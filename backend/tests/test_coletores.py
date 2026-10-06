import httpx
import pytest
import respx
from sqlalchemy import select

from conftest import carregar
from rastro.coletores import ibge, siconfi
from rastro.coletores.base import executar
from rastro.models import Coleta, EnteSiconfi, Municipio


def test_ibge_normaliza_municipio_com_hierarquia_completa():
    sp = next(m for m in carregar("ibge_municipios.json") if m["id"] == 3550308)
    assert ibge.normalizar(sp) == {
        "cod_ibge": 3550308,
        "nome": "São Paulo",
        "uf": "SP",
        "regiao": "SE",
        "microrregiao": "São Paulo",
        "mesorregiao": "Metropolitana de São Paulo",
        "regiao_imediata": "São Paulo",
        "regiao_intermediaria": "São Paulo",
    }


def test_ibge_normaliza_municipio_sem_microrregiao():
    # Boa Esperança do Norte/MT foi criado depois de 2017 e não tem micro/mesorregião
    m = next(m for m in carregar("ibge_municipios.json") if m["id"] == 5101837)
    linha = ibge.normalizar(m)
    assert linha["uf"] == "MT"
    assert linha["microrregiao"] is None
    assert linha["mesorregiao"] is None
    assert linha["regiao_imediata"] is not None


@pytest.mark.parametrize(
    ("cod", "esfera", "uf"),
    [(1, "U", None), (35, "E", "SP"), (53, "D", "DF"), (3550308, "M", "SP")],
)
def test_siconfi_normaliza_uf(cod, esfera, uf):
    # o SICONFI devolve uf="BR" para estados/DF e nulo para a União
    e = next(e for e in carregar("siconfi_entes.json")["items"] if e["cod_ibge"] == cod)
    linha = siconfi.normalizar(e)
    assert (linha["esfera"], linha["uf"]) == (esfera, uf)


def test_siconfi_normaliza_capital():
    itens = {e["cod_ibge"]: e for e in carregar("siconfi_entes.json")["items"]}
    assert siconfi.normalizar(itens[3550308])["capital"] is True
    assert siconfi.normalizar(itens[3500105])["capital"] is False


@respx.mock
def test_siconfi_percorre_paginas():
    itens = carregar("siconfi_entes.json")["items"]
    rota = respx.get(siconfi.URL_ENTES)
    rota.side_effect = [
        httpx.Response(200, json={"items": itens[:4], "hasMore": True}),
        httpx.Response(200, json={"items": itens[4:], "hasMore": False}),
    ]
    with httpx.Client() as client:
        resultado = list(siconfi.paginas(client, siconfi.URL_ENTES, limite=4))
    assert len(resultado) == len(itens)
    assert rota.calls[1].request.url.params["offset"] == "4"


@respx.mock
def test_coleta_ibge_grava_e_atualiza(session):
    respx.get(ibge.URL_MUNICIPIOS).respond(json=carregar("ibge_municipios.json"))
    with httpx.Client() as client:
        assert ibge.coletar(session, client) == 3
        # rodar de novo não duplica (upsert)
        assert ibge.coletar(session, client) == 3
    assert len(session.scalars(select(Municipio)).all()) == 3


@respx.mock
def test_coleta_siconfi_grava(session):
    respx.get(siconfi.URL_ENTES).respond(json=carregar("siconfi_entes.json"))
    with httpx.Client() as client:
        assert siconfi.coletar(session, client) == 6
    assert session.get(EnteSiconfi, 53).uf == "DF"


@respx.mock
def test_executar_registra_falha(session):
    respx.get(ibge.URL_MUNICIPIOS).respond(status_code=503)
    with httpx.Client() as client:
        coleta = executar(session, "ibge-municipios", ibge.coletar, client)
    assert coleta.status == "falha"
    assert "503" in coleta.erro
    assert session.scalars(select(Coleta)).one().finalizada_em is not None
