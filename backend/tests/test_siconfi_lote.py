import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import select

from conftest import carregar
from rastro.coletores import siconfi_demonstrativos as sd
from rastro.coletores import siconfi_lote as sl
from rastro.coletores.base import LimiteDeTaxa
from rastro.models import EnteSiconfi, EntregaSiconfi, ExtratoColetado, ItemLote, LoteColeta


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
    # nada mais a tentar: o lote é finalizado (antes ficava aberto para sempre, e nenhuma
    # execução seguinte relia os extratos); o próximo lote começa do zero
    assert session.scalars(select(LoteColeta)).one().finalizado_em is not None
    novo, retomado = sl.abrir_lote(session, entes, [2025], "x")
    assert not retomado and novo.id != lote.id


@respx.mock
def test_extrato_fica_gravado(session, entes):
    lote, _ = sl.abrir_lote(session, entes[:1], [2025], "y")
    _mock()
    with httpx.Client() as client:
        sl.executar_lote(session, client, lote)
    entregaveis = session.scalars(select(EntregaSiconfi.entregavel)).all()
    assert "MSC Agregada" in entregaveis  # todo o extrato é guardado, não só RREO/RGF
    assert len(entregaveis) == len(carregar("siconfi_extrato_adamantina_2025.json")["items"])


@respx.mock
def test_limite_de_tempo_deixa_o_resto_para_a_proxima_execucao(session, entes):
    lote, _ = sl.abrir_lote(session, entes[:1], [2024, 2025], "z")
    _mock()
    with httpx.Client() as client:
        resumo = sl.executar_lote(session, client, lote, limite_segundos=0)
    # tempo esgotado antes do primeiro item: nada é consultado e o lote continua aberto
    assert resumo["parado_por_tempo"] and resumo["a_tentar"] == 2
    assert len(respx.calls) == 0 and lote.finalizado_em is None
    with httpx.Client() as client:
        resumo = sl.executar_lote(session, client, lote, limite_segundos=3600)
    assert not resumo["parado_por_tempo"]
    assert (resumo["sucesso"], resumo["a_tentar"]) == (2, 0)
    assert lote.finalizado_em is not None


@pytest.fixture
def entes_de_duas_ufs(session):
    lista = [
        EnteSiconfi(cod_ibge=3550308, nome="São Paulo", esfera="M", uf="SP", regiao="SE",
                    capital=True, exercicio=2026),
        EnteSiconfi(cod_ibge=3500105, nome="Adamantina", esfera="M", uf="SP", regiao="SE",
                    capital=False, exercicio=2026),
        EnteSiconfi(cod_ibge=1400100, nome="Boa Vista", esfera="M", uf="RR", regiao="N",
                    capital=True, exercicio=2026),
        EnteSiconfi(cod_ibge=14, nome="Roraima", esfera="E", uf="RR", regiao="N",
                    capital=False, exercicio=2026),
    ]  # fmt: skip
    session.add_all(lista)
    session.commit()
    return lista


@respx.mock
def test_ordem_nacional_uf_menor_primeiro_e_exercicios_prioritarios(session, entes_de_duas_ufs):
    # resposta real de extrato vazio (Brasília, 2024): nenhum relatório a baixar
    respx.get(sd.URL_EXTRATO).respond(
        json=carregar("siconfi_extrato_brasilia_5300108_2024_vazio.json")
    )
    anos = [2022, 2023, 2024, 2025]
    lote, _ = sl.abrir_lote(session, entes_de_duas_ufs, anos, "nacional")
    with httpx.Client() as client:
        sl.executar_lote(session, client, lote, prioridade=[2024, 2025])
    ordem = [
        (int(c.request.url.params["id_ente"]), int(c.request.url.params["an_referencia"]))
        for c in respx.calls
    ]
    assert ordem == [
        # 1º: os exercícios prioritários, UF por UF (RR tem 1 município, SP tem 2)
        (14, 2024), (14, 2025), (1400100, 2024), (1400100, 2025),
        (3500105, 2024), (3500105, 2025), (3550308, 2024), (3550308, 2025),
        # depois: os demais, do mais recente para o mais antigo
        (14, 2023), (14, 2022), (1400100, 2023), (1400100, 2022),
        (3500105, 2023), (3500105, 2022), (3550308, 2023), (3550308, 2022),
    ]  # fmt: skip


def test_rodizio_dos_exercicios_antigos(session, entes_de_duas_ufs):
    agora = datetime(2026, 10, 12, 4, 20, tzinfo=UTC)  # semana ISO 42: rodízio 42 % 4 = 2
    lidos = {
        (14, 2024): agora - timedelta(days=10),  # 14 % 4 = 2: semana dele
        (14, 2023): agora - timedelta(days=2),  # semana dele, mas lido há 2 dias
        (1400100, 2024): agora - timedelta(days=10),  # 1400100 % 4 = 0: fora da semana
        (3500105, 2024): agora - timedelta(days=40),  # fora da semana, mas há mais de 35 dias
        # (3550308, 2024): nunca lido
    }
    session.add_all(
        ExtratoColetado(cod_ibge=c, exercicio=a, itens=0, lido_em=lido)
        for (c, a), lido in lidos.items()
    )
    session.commit()
    incluir = sl.rodizio(session, agora)
    por_cod = {e.cod_ibge: e for e in entes_de_duas_ufs}
    # exercício corrente e anterior: sempre
    assert all(incluir(e, a) for e in entes_de_duas_ufs for a in (2025, 2026))
    assert incluir(por_cod[14], 2024)
    assert not incluir(por_cod[14], 2023)
    assert not incluir(por_cod[1400100], 2024)
    assert incluir(por_cod[3500105], 2024)
    assert incluir(por_cod[3550308], 2024)

    lote, _ = sl.abrir_lote(session, entes_de_duas_ufs, [2024, 2025], "r", incluir=incluir)
    itens = set(session.execute(select(ItemLote.cod_ibge, ItemLote.exercicio)).all())
    assert (1400100, 2024) not in itens and (14, 2024) in itens and len(itens) == 7
