"""Metodologia v1.1, com respostas reais gravadas da API do SICONFI.

Votuporanga/SP (2024): dois consórcios entregam RREO e RGF com o código do município. Os
indicadores têm de usar o relatório da Prefeitura (D1). Valores conferidos na API em
08/10/2026.
"""

from decimal import Decimal as D

import httpx
import pytest
import respx

from conftest import carregar
from rastro import indicadores as ind
from rastro.coletores import siconfi_demonstrativos as sd
from rastro.coletores.arquivo import ArquivoBruto
from rastro.coletores.base import novo_cliente
from rastro.models import EnteSiconfi

VOTUPORANGA = 3557105


@pytest.fixture
def votuporanga(session):
    e = EnteSiconfi(cod_ibge=VOTUPORANGA, nome="Votuporanga", esfera="M", uf="SP",
                    regiao="SE", capital=False, populacao=96795, exercicio=2026)  # fmt: skip
    session.add(e)
    session.commit()
    with respx.mock:
        respx.get(sd.URL_EXTRATO).respond(json=carregar("votuporanga_2024_extrato.json"))
        respx.get(sd.URL_RREO).respond(json=carregar("votuporanga_2024_rreo6.json"))
        for poder in "EL":
            respx.get(sd.URL_RGF, params__contains={"co_poder": poder}).respond(
                json=carregar(f"votuporanga_2024_rgf3_{poder}.json")
            )
        with httpx.Client() as client:
            sd.coletar_ente(session, client, e, 2024)
    return e


def test_indicadores_usam_a_prefeitura_e_nao_o_consorcio(session, votuporanga):
    a = ind.autonomia(session, VOTUPORANGA, 2024)
    assert a["instituicao"] == "Prefeitura Municipal de Votuporanga - SP"
    assert a["receita_tributaria"] == D("121426387.08")
    assert a["despesa_administracao"] == D("35613252.29")
    assert a["razao"] == D("5.6986")

    i = ind.investimento(session, VOTUPORANGA, 2024)
    assert i["receita_realizada"] == D("639186924.37")  # do consórcio: 347.779,50
    assert i["percentual"] == D("5.6160")

    liq = ind.liquidez(session, VOTUPORANGA, 2024)
    assert liq["instituicao"] == "Prefeitura Municipal de Votuporanga - SP"
    assert liq["caixa_liquido_nao_vinculado"] == D("86887342.42")
    assert liq["percentual"] == D("16.5639")


GASTAO_VIDIGAL = 3516804


@pytest.fixture
def gastao_vidigal(session, engine):
    e = EnteSiconfi(cod_ibge=GASTAO_VIDIGAL, nome="Gastão Vidigal", esfera="M", uf="SP",
                    regiao="SE", capital=False, populacao=4383, exercicio=2026)  # fmt: skip
    session.add(e)
    session.commit()
    with respx.mock:
        respx.get(sd.URL_EXTRATO).respond(json=carregar("gastao_vidigal_2024_extrato.json"))
        respx.get(sd.URL_RREO).respond(json={"items": [], "hasMore": False})
        for poder in "EL":
            respx.get(sd.URL_RGF, params__contains={"co_poder": poder}).respond(
                json=carregar(f"gastao_vidigal_2024_rgf_s2_{poder}.json")
            )
        # com o arquivo bruto: o teste de reconstrução lê as respostas guardadas
        with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as client:
            sd.coletar_ente(session, client, e, 2024)
    return e


def test_linha_nao_vinculados_omitida_vem_do_total(session, gastao_vidigal):
    """RGF Anexo 5 de Gastão Vidigal (2º semestre de 2024): a API não traz a linha (I),
    mas o total (IV) = II + III mostra que ela é zero (D2)."""
    liq = ind.liquidez(session, GASTAO_VIDIGAL, 2024)
    assert liq["caixa_liquido_nao_vinculado"] == D("0")
    assert liq["nao_vinculados_derivado"] is True
    assert liq["rcl"] == D("27289324.76")
    assert liq["percentual"] == D("0")
    assert liq["caixa_liquido_vinculado"] == D("2490310.97")


def test_linha_nao_vinculados_presente_nao_e_derivada(session, votuporanga):
    assert ind.liquidez(session, VOTUPORANGA, 2024)["nao_vinculados_derivado"] is False


def test_mapeamento_novo_e_reconstruido_do_bruto_uma_vez(session, gastao_vidigal):
    """Linhas "TOTAL (IV)" coletadas antes do mapeamento v2 vêm do arquivo bruto."""
    from sqlalchemy import delete, select

    from rastro import reconstrucao
    from rastro.models import ContaDemonstrativo

    total_iv = ContaDemonstrativo.conta.startswith("TOTAL (IV)")
    # simula o banco de antes do mapeamento v2: sem as linhas do total
    session.execute(delete(ContaDemonstrativo).where(total_iv))
    session.commit()
    assert ind.liquidez(session, GASTAO_VIDIGAL, 2024)["caixa_liquido_nao_vinculado"] is None

    r = reconstrucao.aplicar_mapeamento(session, tipo="RGF", se_mudou=True)
    assert r["reconstruidas"] > 0 and not r["pulado"]
    assert session.scalars(select(ContaDemonstrativo).where(total_iv)).first() is not None
    assert ind.liquidez(session, GASTAO_VIDIGAL, 2024)["caixa_liquido_nao_vinculado"] == D("0")
    # a mesma versão não é aplicada de novo
    assert reconstrucao.aplicar_mapeamento(session, tipo="RGF", se_mudou=True)["pulado"]


def test_per_capita_usa_a_populacao_oficial_do_ano(session, votuporanga):
    """D6: população do IBGE mais recente até o ano do exercício (respostas reais gravadas
    das tabelas 6579 e 4709 do SIDRA)."""
    from rastro.coletores.ibge import TABELA_CENSO_2022, TABELA_POPULACAO, normalizar_populacao
    from rastro.models import PopulacaoIbge

    for arquivo, tabela in (
        ("ibge_populacao_6579_3anos.json", TABELA_POPULACAO),
        ("ibge_censo2022_4709.json", TABELA_CENSO_2022),
    ):
        session.add_all(
            PopulacaoIbge(**linha, tabela=tabela)
            for linha in normalizar_populacao(carregar(arquivo))
        )
    session.commit()

    pc = ind.indicadores(session, VOTUPORANGA, 2024)["per_capita"]
    assert (pc["populacao"], pc["ano_populacao"]) == (100159, 2024)
    assert "6579" in pc["fonte_populacao"]
    # (121.426.387,08 + 119.893.281,53) / 100.159
    assert pc["receita_local"] == D("2409.37")
    assert pc["investimento_liquidado"] == D("358.40")  # 35.896.827,32 / 100.159

    # 2023: a tabela 6579 não tem 2022 nem 2023; vale o Censo 2022
    pc23 = ind.per_capita(session, VOTUPORANGA, 2023, None, None)
    assert (pc23["populacao"], pc23["ano_populacao"]) == (96634, 2022)
    assert "Censo" in pc23["fonte_populacao"]
