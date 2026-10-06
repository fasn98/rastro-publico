import time

import httpx
import pytest
import respx
from sqlalchemy import select

from conftest import carregar
from rastro.coletores import siconfi_demonstrativos as sd
from rastro.coletores import siconfi_lote as sl
from rastro.coletores.base import LimiteDeTaxa
from rastro.models import EnteSiconfi, EntregaSiconfi, ItemLote, LoteColeta


@pytest.mark.parametrize(
    ("texto", "anos"),
    [("2022-2025", [2022, 2023, 2024, 2025]), ("2025,2022", [2022, 2025]), ("2024", [2024])],
)
def test_interpretar_anos(texto, anos):
    assert sl.interpretar_anos(texto) == anos


def test_limite_de_taxa_espaca_requisicoes():
    limite = LimiteDeTaxa(20)  # 50 ms entre requisições
    inicio = time.monotonic()
    for _ in range(4):
        limite(None)
    assert time.monotonic() - inicio >= 0.15  # 3 intervalos


def test_limite_zero_nao_espera():
    limite = LimiteDeTaxa(0)
    inicio = time.monotonic()
    for _ in range(100):
        limite(None)
    assert time.monotonic() - inicio < 0.05


@pytest.fixture
def entes(session):
    lista = [
        EnteSiconfi(cod_ibge=3500105, nome="Adamantina", esfera="M", uf="SP", regiao="SE",
                    capital=False, exercicio=2026),
        EnteSiconfi(cod_ibge=9999999, nome="Quebrado", esfera="M", uf="SP", regiao="SE",
                    capital=False, exercicio=2026),
    ]  # fmt: skip
    session.add_all(lista)
    session.commit()
    return lista


def _mock(falhar_quebrado=True):
    if falhar_quebrado:
        respx.get(sd.URL_EXTRATO, params__contains={"id_ente": "9999999"}).respond(500)
    respx.get(sd.URL_EXTRATO).respond(json=carregar("siconfi_extrato_adamantina_2025.json"))
    respx.get(sd.URL_RREO).respond(json=carregar("siconfi_rreo_simplificado.json"))
    respx.get(sd.URL_RGF, params__contains={"co_poder": "E"}).respond(
        json=carregar("siconfi_rgf_simplificado_E.json")
    )
    respx.get(sd.URL_RGF, params__contains={"co_poder": "L"}).respond(
        json=carregar("siconfi_rgf_simplificado_L.json")
    )


@respx.mock
def test_lote_retoma_e_tenta_de_novo_so_o_que_falhou(session, entes):
    chave = sl.chave_lote(["SP"], [2025], [], ["M"])
    lote, retomado = sl.abrir_lote(session, entes, [2025], chave)
    assert not retomado
    _mock()
    with httpx.Client() as client:
        resumo = sl.executar_lote(session, client, lote)
    assert (resumo["sucesso"], resumo["falha"]) == (1, 1)
    assert lote.finalizado_em is None

    # mesma chave: retoma o mesmo lote em vez de criar outro
    mesmo, retomado = sl.abrir_lote(session, entes, [2025], chave)
    assert (mesmo.id, retomado) == (lote.id, True)

    respx.clear()  # remove as rotas (inclusive a que devolvia 500)
    respx.reset()  # zera o histórico de chamadas
    _mock(falhar_quebrado=False)
    with httpx.Client() as client:
        resumo = sl.executar_lote(session, client, mesmo)
    assert (resumo["sucesso"], resumo["falha"]) == (2, 0)
    # na retomada, só o item que falhou consultou o extrato de novo
    ids = [c.request.url.params["id_ente"] for c in respx.calls if "extrato" in str(c.request.url)]
    assert ids == ["9999999"]
    assert mesmo.finalizado_em is not None
    tentativas = dict(session.execute(select(ItemLote.cod_ibge, ItemLote.tentativas)).all())
    assert tentativas == {3500105: 1, 9999999: 2}


@respx.mock
def test_lote_respeita_max_tentativas(session, entes):
    lote, _ = sl.abrir_lote(session, entes, [2025], "x")
    _mock()
    with httpx.Client() as client:
        sl.executar_lote(session, client, lote, max_tentativas=1)
        extratos = len(respx.calls)
        resumo = sl.executar_lote(session, client, lote, max_tentativas=1)
    assert resumo["falha"] == 1
    assert len(respx.calls) == extratos  # esgotado: não tenta de novo
    assert session.scalars(select(LoteColeta)).one().finalizado_em is None


@respx.mock
def test_extrato_fica_gravado(session, entes):
    lote, _ = sl.abrir_lote(session, entes[:1], [2025], "y")
    _mock()
    with httpx.Client() as client:
        sl.executar_lote(session, client, lote)
    entregaveis = session.scalars(select(EntregaSiconfi.entregavel)).all()
    assert "MSC Agregada" in entregaveis  # todo o extrato é guardado, não só RREO/RGF
    assert len(entregaveis) == len(carregar("siconfi_extrato_adamantina_2025.json")["items"])
