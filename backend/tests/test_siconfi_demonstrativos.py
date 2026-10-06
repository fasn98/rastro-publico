import copy
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx
from sqlalchemy import func, select

from conftest import carregar
from rastro.coletores import siconfi_demonstrativos as sd
from rastro.coletores.base import executar
from rastro.models import ContaDemonstrativo, DemonstrativoSiconfi, EnteSiconfi

ADAMANTINA = EnteSiconfi(cod_ibge=3500105, nome="Adamantina", esfera="M", uf="SP")


def _extrato():
    return carregar("siconfi_extrato_adamantina_2025.json")


def _mock_api(extrato=None):
    """Simula o SICONFI para Adamantina/2025 e devolve as rotas para inspeção."""
    rotas = {
        "extrato": respx.get(sd.URL_EXTRATO).respond(json=extrato or _extrato()),
        "rreo": respx.get(sd.URL_RREO).respond(json=carregar("siconfi_rreo_simplificado.json")),
        "rgf_E": respx.get(sd.URL_RGF, params__contains={"co_poder": "E"}).respond(
            json=carregar("siconfi_rgf_simplificado_E.json")
        ),
        "rgf_L": respx.get(sd.URL_RGF, params__contains={"co_poder": "L"}).respond(
            json=carregar("siconfi_rgf_simplificado_L.json")
        ),
    }
    return rotas


@respx.mock
def test_entregas_filtra_rreo_rgf_e_usa_data_mais_recente():
    _mock_api()
    with httpx.Client() as client:
        itens = sd.entregas(client, 3500105, 2025)
    # a MSC Agregada do extrato é ignorada
    assert [(e.demonstrativo, e.periodicidade, e.periodo) for e in itens] == [
        ("RGF Simplificado", "S", 2),
        ("RREO Simplificado", "B", 2),
        ("RREO Simplificado", "B", 6),
    ]
    # o RGF S2 tem duas entregas (Câmara em jan/2026, Prefeitura em mar/2026): vale a última
    assert itens[0].data_status == datetime(2026, 3, 20, 22, 30, 37, tzinfo=UTC)


@respx.mock
def test_coleta_grava_por_poder_com_valores_exatos(session):
    rotas = _mock_api()
    with httpx.Client() as client:
        total = sd.coletar_ente(session, client, ADAMANTINA, 2025)

    assert total == 20  # 2 RREO x 5 linhas + RGF (E e L) x 5 linhas
    cabecalhos = session.scalars(
        select(DemonstrativoSiconfi).order_by(
            DemonstrativoSiconfi.demonstrativo,
            DemonstrativoSiconfi.periodo,
            DemonstrativoSiconfi.poder,
        )  # fmt: skip
    ).all()
    assert [(c.demonstrativo, c.periodo, c.poder) for c in cabecalhos] == [
        ("RGF Simplificado", 2, "E"),
        ("RGF Simplificado", 2, "L"),
        ("RREO Simplificado", 2, None),
        ("RREO Simplificado", 6, None),
    ]
    assert cabecalhos[1].instituicao == "Câmara de Vereadores de Adamantina - SP"
    # RGF de município: só consulta Executivo e Legislativo
    poderes = {c.request.url.params["co_poder"] for c in respx.calls if "rgf" in str(c.request.url)}
    assert poderes == {"E", "L"}
    assert rotas["rreo"].calls[0].request.url.params["co_tipo_demonstrativo"] == (
        "RREO Simplificado"
    )
    # valores monetários sem erro de ponto flutuante
    valor = session.scalar(
        select(ContaDemonstrativo.valor)
        .join(DemonstrativoSiconfi)
        .where(DemonstrativoSiconfi.poder == "E", ContaDemonstrativo.coluna.is_not(None))
        .order_by(ContaDemonstrativo.id)
        .limit(1)
    )
    assert valor == Decimal("8277279.17")


@respx.mock
def test_rgf_separa_instituicoes_do_mesmo_poder(session):
    # No Legislativo de São Paulo, Câmara e Tribunal de Contas do Município entregam
    # cada um o seu RGF, e a API devolve as linhas dos dois juntas.
    rgf_l = carregar("siconfi_rgf_simplificado_L.json")
    tcm = copy.deepcopy(rgf_l["items"][:2])
    for linha in tcm:
        linha["instituicao"] = "Tribunal de Contas do Município"
        linha["valor"] = 1
    rgf_l["items"] += tcm
    _mock_api()
    respx.get(sd.URL_RGF, params__contains={"co_poder": "L"}).respond(json=rgf_l)
    with httpx.Client() as client:
        sd.coletar_ente(session, client, ADAMANTINA, 2025)

    legislativo = session.scalars(
        select(DemonstrativoSiconfi)
        .where(DemonstrativoSiconfi.poder == "L")
        .order_by(DemonstrativoSiconfi.instituicao)
    ).all()
    assert [(d.instituicao, d.linhas) for d in legislativo] == [
        ("Câmara de Vereadores de Adamantina - SP", 5),
        ("Tribunal de Contas do Município", 2),
    ]
    assert {c.valor for c in legislativo[1].contas} == {1}


@respx.mock
def test_segunda_coleta_so_le_o_extrato(session):
    rotas = _mock_api()
    with httpx.Client() as client:
        sd.coletar_ente(session, client, ADAMANTINA, 2025)
        chamadas = rotas["rreo"].call_count
        assert sd.coletar_ente(session, client, ADAMANTINA, 2025) == 0
    assert rotas["rreo"].call_count == chamadas
    assert rotas["extrato"].call_count == 2


@respx.mock
def test_retificacao_substitui_so_o_relatorio_alterado(session):
    _mock_api()
    with httpx.Client() as client:
        sd.coletar_ente(session, client, ADAMANTINA, 2025)

    retificado = copy.deepcopy(_extrato())
    for item in retificado["items"]:
        if item["entregavel"].startswith("Relatório Resumido") and item["periodo"] == 6:
            item["data_status"] = "2026-07-01T10:00:00Z"
    respx.reset()
    rotas = _mock_api(retificado)
    with httpx.Client() as client:
        assert sd.coletar_ente(session, client, ADAMANTINA, 2025) == 5

    assert rotas["rreo"].call_count == 1
    assert rotas["rreo"].calls[0].request.url.params["nr_periodo"] == "6"
    assert not rotas["rgf_E"].called
    # substituiu em vez de duplicar
    assert session.scalar(select(func.count()).select_from(ContaDemonstrativo)) == 20
    b6 = session.scalars(
        select(DemonstrativoSiconfi).where(DemonstrativoSiconfi.periodo == 6)
    ).one()
    assert b6.data_status == datetime(2026, 7, 1, 10, tzinfo=UTC)


@respx.mock
def test_forcar_baixa_de_novo(session):
    rotas = _mock_api()
    with httpx.Client() as client:
        sd.coletar_ente(session, client, ADAMANTINA, 2025)
        assert sd.coletar_ente(session, client, ADAMANTINA, 2025, forcar=True) == 20
    assert rotas["rreo"].call_count == 4
    assert session.scalar(select(func.count()).select_from(ContaDemonstrativo)) == 20


@respx.mock
def test_falha_em_um_ente_nao_impede_os_outros(session):
    # registrada antes das rotas genéricas: o respx usa a primeira que casar
    respx.get(sd.URL_EXTRATO, params__contains={"id_ente": "9999999"}).respond(status_code=500)
    _mock_api()
    quebrado = EnteSiconfi(cod_ibge=9999999, nome="Quebrado", esfera="M", uf="SP")
    with httpx.Client() as client:
        coleta = executar(
            session, "siconfi-demonstrativos", sd.coletor([quebrado, ADAMANTINA], [2025]), client
        )
    assert coleta.status == "parcial"
    assert coleta.registros == 20
    assert coleta.erro.startswith("9999999 2025: HTTPStatusError")


@respx.mock
def test_falha_total_fica_registrada_como_falha(session):
    respx.get(sd.URL_EXTRATO).respond(status_code=500)
    with httpx.Client() as client:
        coleta = executar(
            session, "siconfi-demonstrativos", sd.coletor([ADAMANTINA], [2025]), client
        )
    assert coleta.status == "falha"


@pytest.mark.parametrize(
    ("esfera", "poderes"), [("M", ("E", "L")), ("E", ("E", "L", "J", "M", "D"))]
)
def test_poderes_por_esfera(esfera, poderes):
    assert sd.PODERES_POR_ESFERA[esfera] == poderes
