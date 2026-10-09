"""Coleta dos políticos para várias UFs (aprovada em 09/10/2026): passada única da Câmara,
reaproveitamento dos anos fechados e das eleições anteriores do TSE, e limite de tempo.

Respostas reais gravadas em tests/fixtures/politicos (as mesmas de test_politicos,
test_cota_emendas e test_tse).
"""

from datetime import UTC, datetime, timedelta

import pytest
import respx
from sqlalchemy import select
from test_cota_emendas import _zip_cota
from test_politicos import JSON, _json, _mock_camara
from test_tse import AMOSTRA_IBGE
from test_tse import _mock as _mock_tse

from rastro.coletores.arquivo import ArquivoBruto
from rastro.coletores.base import ColetaParcial, novo_cliente
from rastro.politicos import camara, coletar, reuso, tse
from rastro.politicos.comum import upsert_politico
from rastro.politicos.modelos import DEPUTADO_FEDERAL, PolPolitico

# com "hoje" em 2027, 2025 é ano fechado; em 2026, não
EM_2027 = datetime(2027, 1, 10, tzinfo=UTC)
EM_2026 = datetime(2026, 10, 9, tzinfo=UTC)


@pytest.fixture
def cliente(engine):
    with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
        yield c


def _mock_camara_com_cota() -> None:
    _mock_camara()
    respx.get(url__regex=rf"{camara.API}/deputados/\d+/historico").respond(
        content=_json("camara_historico_220637.json"), headers=JSON
    )
    respx.get(camara.URL_COTA.format(ano=2025)).respond(content=_zip_cota())


def _rotas() -> dict[str, respx.Route]:
    """Rotas da Câmara por nome, conferindo o endereço de cada uma."""
    rotas = {}
    for r in respx.routes:
        texto = repr(r.pattern)
        for nome, trecho in (
            ("proposicoes", "/proposicoes"),
            ("votos", "votacoesVotos-2025"),
            ("presencas", "eventosPresencaDeputados-2025"),
            ("cota", "Ano-2025.csv.zip"),
            ("historico", "historico"),
        ):
            if trecho in texto:
                rotas[nome] = r
    assert len(rotas) == 5, rotas
    return rotas


def _zerar(rotas) -> None:
    for r in rotas.values():
        r.reset()


@respx.mock
def test_ano_fechado_nao_e_baixado_de_novo_na_mesma_semana(session, cliente):
    _mock_camara_com_cota()
    rotas = _rotas()
    coletor = coletar.coletor_camara(["SP"], [2025], hoje=EM_2027)

    primeira = coletor(session, cliente)
    assert all(r.called for r in rotas.values())
    _zerar(rotas)

    segunda = coletor(session, cliente)
    # anos fechados: nada de proposições, votos, presenças nem cota; o histórico, sim
    assert rotas["historico"].called
    assert {n: rotas[n].call_count for n in ("proposicoes", "votos", "presencas", "cota")} == {
        "proposicoes": 0,
        "votos": 0,
        "presencas": 0,
        "cota": 0,
    }
    assert segunda < primeira


@respx.mock
def test_ano_corrente_e_o_anterior_sempre_sao_baixados(session, cliente):
    _mock_camara_com_cota()
    rotas = _rotas()
    coletor = coletar.coletor_camara(["SP"], [2025], hoje=EM_2026)
    coletor(session, cliente)
    _zerar(rotas)
    coletor(session, cliente)
    assert all(r.called for r in rotas.values())


@respx.mock
def test_ano_fechado_e_baixado_de_novo_sem_a_copia_arquivada(session):
    _mock_camara_com_cota()
    rotas = _rotas()
    coletor = coletar.coletor_camara(["SP"], [2025], hoje=EM_2027)
    # sem arquivamento das respostas, a auditoria não levaria a nada: nada é reaproveitado
    with novo_cliente(req_por_segundo=0, arquivo=False) as sem_arquivo:
        coletor(session, sem_arquivo)
        _zerar(rotas)
        coletor(session, sem_arquivo)
    assert all(r.called for r in rotas.values())


@respx.mock
def test_uf_nova_faz_o_arquivo_fechado_ser_baixado_de_novo(session, cliente):
    _mock_camara_com_cota()
    coletar.coletor_camara(["SP"], [2025], hoje=EM_2027)(session, cliente)
    # os votos de 2025 vieram de um download que cobriu SP, mas não a BA
    assert reuso.ufs_com_arquivo_recente(session, "votos", 2025) == {"SP"}
    assert not {"SP", "BA"} <= reuso.ufs_com_arquivo_recente(session, "votos", 2025)
    # passada a semana, nem SP
    depois = datetime.now(UTC) + reuso.IDADE_MAXIMA + timedelta(minutes=1)
    assert reuso.ufs_com_arquivo_recente(session, "votos", 2025, agora=depois) == set()


@respx.mock
def test_limite_de_tempo_para_antes_do_proximo_item(session, cliente):
    _mock_camara()
    rotas_hist = respx.get(url__regex=rf"{camara.API}/deputados/\d+/historico").respond(
        content=_json("camara_historico_220637.json"), headers=JSON
    )
    relogio = iter([0.0, 30.0, 61.0])  # início, 1º item (dentro do prazo), 2º item (fora)
    prazo = coletar.Prazo(1, relogio=lambda: next(relogio))
    with pytest.raises(ColetaParcial) as erro:
        coletar.coletor_camara(["SP"], [2025], prazo)(session, cliente)
    assert erro.value.erros == ["limite de tempo de 1 min atingido"]
    assert rotas_hist.call_count == 1


def test_sem_limite_de_tempo_por_padrao():
    assert not coletar.Prazo(0).esgotado() and not coletar.SEM_PRAZO.esgotado()


@respx.mock
def test_eleicao_anterior_do_tse_reaproveitada_so_com_copia_recente(session, cliente):
    _mock_tse()
    tse.coletar_eleitos(session, cliente, 2024, "SP", AMOSTRA_IBGE)
    assert reuso.tse_recente(session, 2024, "SP")
    assert not reuso.tse_recente(session, 2024, "RJ")
    depois = datetime.now(UTC) + reuso.IDADE_MAXIMA + timedelta(minutes=1)
    assert not reuso.tse_recente(session, 2024, "SP", agora=depois)


def test_ano_fechado():
    assert reuso.ano_fechado(2024, EM_2026) and not reuso.ano_fechado(2025, EM_2026)
    assert reuso.ano_fechado(2025, EM_2027)


def test_uf_desconhecida_e_recusada(capsys):
    with pytest.raises(SystemExit):
        coletar.main(["--uf", "XX", "--fontes", "tse"])
    assert "UF desconhecida: XX" in capsys.readouterr().err


@respx.mock  # sem rotas: qualquer download falharia
def test_df_nao_tem_eleicao_municipal(session, cliente):
    assert coletar.coletor_tse("DF", [2024], hoje=EM_2026)(session, cliente) == 0
    assert coletar.coletor_prefeitos("DF")(session, cliente) == 0
    assert not respx.calls


def test_partido_de_quem_passou_por_varios_partidos(session):
    # deputado do CE na lista da legislatura 57 (API da Câmara, 09/10/2026): 36 caracteres
    upsert_politico(
        session,
        {
            "fonte": "camara",
            "id_fonte": "234673",
            "cargo": DEPUTADO_FEDERAL,
            "nome": "Vanderlan Alves",
            "partido": "UNIÃO / REPUBLICANOS / SOLIDARIEDADE",
            "uf": "CE",
            "legislatura": 57,
            "em_exercicio": False,
            "url_fonte": "https://dadosabertos.camara.leg.br/api/v2/deputados/234673",
            "url_pagina": "https://www.camara.leg.br/deputados/234673",
        },
    )
    session.commit()
    assert session.scalar(select(PolPolitico.partido)) == "UNIÃO / REPUBLICANOS / SOLIDARIEDADE"
