"""Novos indicadores, de ponta a ponta: respostas reais gravadas de Adamantina/SP (2025)
passam pelo coletor e os valores calculados têm de bater com os aprovados."""

import copy
from decimal import Decimal as D

import httpx
import pytest
import respx

from conftest import carregar
from rastro import indicadores as ind
from rastro.coletores import siconfi_demonstrativos as sd
from rastro.models import EnteSiconfi

COD = 3500105


def _mock(extrato=None):
    respx.get(sd.URL_EXTRATO).respond(json=extrato or carregar("adamantina_2025_extrato.json"))
    respx.get(sd.URL_RREO).respond(json=carregar("adamantina_2025_rreo6.json"))
    for poder in "EL":
        respx.get(sd.URL_RGF, params__contains={"co_poder": poder}).respond(
            json=carregar(f"adamantina_2025_rgf2_{poder}.json")
        )


@pytest.fixture
def ente(session):
    e = EnteSiconfi(cod_ibge=COD, nome="Adamantina", esfera="M", uf="SP", regiao="SE",
                    capital=False, populacao=35673, exercicio=2026)  # fmt: skip
    session.add(e)
    session.commit()
    return e


@pytest.fixture
def coletado(session, ente):
    with respx.mock:
        _mock()
        with httpx.Client() as client:
            sd.coletar_ente(session, client, ente, 2025)
    return ente


def test_autonomia(session, coletado):
    a = ind.autonomia(session, COD, 2025)
    assert a["receita_tributaria"] == D("54320675.49")
    assert (a["cota_icms"], a["cota_ipva"], a["cota_itr"]) == (
        D("32333297.62"), D("14556460.07"), D("401677.86"),
    )  # fmt: skip
    # só as linhas de FUNÇÃO; subfunções ("Administração Geral"...) ficam de fora
    assert a["despesa_administracao"] == D("20599329.05")
    assert a["despesa_legislativa"] == D("2991196.63")
    assert a["razao"] == D("4.3073")


def test_liquidez_nao_vinculados_e_contexto(session, coletado):
    liq = ind.liquidez(session, COD, 2025)
    assert liq["caixa_liquido_nao_vinculado"] == D("69277622.76")
    assert liq["rcl"] == D("315919914.69")
    assert liq["percentual"] == D("21.9289")
    assert liq["percentual_com_vinculados"] == D("24.2562")  # (I + II), fora da nota


def test_investimento_liquidado_com_contexto(session, coletado):
    inv = ind.investimento(session, COD, 2025)
    assert inv["percentual"] == D("1.9471")
    assert inv["empenhado"] == D("11264757.63")
    assert inv["restos_a_pagar_nao_processados"] == D("5046694.01")


def test_transparencia_completa(session, coletado):
    t = ind.transparencia(session, COD, 2025)
    assert t["periodicidade_rgf"] == "S"
    assert t["indice"] == D("1")
    assert t["blocos"]["rgf_legislativo"] == {"disponiveis": 2, "esperados": 2}


def test_transparencia_parcial(session, ente):
    extrato = copy.deepcopy(carregar("adamantina_2025_extrato.json"))
    extrato["items"] = [
        i for i in extrato["items"]
        if i["entregavel"] != "Balanço Anual (DCA)"
        and not (i["entregavel"].startswith("Relatório Resumido") and i["periodo"] == 3)
    ]  # fmt: skip
    with respx.mock:
        _mock(extrato)
        with httpx.Client() as client:
            sd.coletar_ente(session, client, ente, 2025)
    t = ind.transparencia(session, COD, 2025)
    assert t["blocos"]["rreo"] == {"disponiveis": 5, "esperados": 6}
    assert t["blocos"]["dca"] == {"disponiveis": 0, "esperados": 1}
    assert t["indice"] == D("0.7083")  # (5/6 + 1 + 1 + 0) / 4


def test_transparencia_nao_coletada_e_none(session, ente):
    assert ind.transparencia(session, COD, 2025) is None


def test_liquidez_exige_periodo_final(session, coletado):
    from rastro.models import DemonstrativoSiconfi

    for d in session.query(DemonstrativoSiconfi).filter_by(poder="E"):
        if d.periodo == 2:
            session.delete(d)
    session.commit()
    assert ind.liquidez(session, COD, 2025) is None  # só o 1º semestre: não é dado anual
