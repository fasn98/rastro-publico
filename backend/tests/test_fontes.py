"""Falha de uma fonte: novas tentativas com espera, situação por fonte e resumo no log."""

from datetime import UTC, datetime, timedelta

import httpx
import respx

from rastro import fontes
from rastro.coletores.base import novo_cliente
from rastro.models import Coleta
from rastro.politicos import camara

URL = f"{camara.API}/deputados"


def _coletor(session, client):
    client.get(URL).raise_for_status()
    return 7


def _cliente():
    # sem arquivo bruto (a conexão do arquivo não vê a transação do teste)
    return novo_cliente(req_por_segundo=0, arquivo=False)


@respx.mock
def test_erro_5xx_tenta_de_novo_com_espera_e_conclui(session, monkeypatch):
    monkeypatch.setenv("RASTRO_HTTP_TENTATIVAS", "1")
    from rastro.config import get_settings

    get_settings.cache_clear()
    rota = respx.get(URL).mock(
        side_effect=[httpx.Response(504), httpx.Response(504), httpx.Response(200, json={})]
    )
    esperas = []
    coleta = fontes.executar_com_esperas(
        session, "pol-camara", _coletor, _cliente, esperas=[60, 120, 240], dormir=esperas.append
    )
    assert coleta.status == "sucesso" and coleta.registros == 7
    assert esperas == [60, 120]  # espera progressiva entre as rodadas
    assert rota.call_count == 3
    get_settings.cache_clear()


@respx.mock
def test_5xx_persistente_registra_resumo_e_traceback(session, monkeypatch):
    monkeypatch.setenv("RASTRO_HTTP_TENTATIVAS", "1")
    from rastro.config import get_settings

    get_settings.cache_clear()
    respx.get(URL).respond(504)
    esperas = []
    coleta = fontes.executar_com_esperas(
        session, "pol-camara", _coletor, _cliente, esperas=[1, 2, 4], dormir=esperas.append
    )
    assert coleta.status == "falha"
    assert esperas == [1, 2, 4]
    primeira, *resto = coleta.erro.splitlines()
    assert primeira == "HTTP 504 após 4 tentativas"
    assert "Traceback (most recent call last)" in "\n".join(resto)
    assert session.query(Coleta).filter_by(fonte="pol-camara").count() == 4
    get_settings.cache_clear()


def test_erro_que_nao_passa_sozinho_nao_e_repetido(session):
    def quebra(s, c):
        raise ValueError("coluna nova no arquivo")

    esperas = []
    coleta = fontes.executar_com_esperas(
        session, "pol-tse", quebra, _cliente, esperas=[1, 2], dormir=esperas.append
    )
    assert coleta.status == "falha" and esperas == []
    assert coleta.erro.startswith("ValueError após 1 tentativa\nValueError: coluna nova")


def _coleta(session, fonte, status, quando, erro=None):
    session.add(
        Coleta(fonte=fonte, status=status, iniciada_em=quando, finalizada_em=quando, erro=erro)
    )
    session.commit()


def test_situacao_e_resumo_das_fontes(session):
    inicio = datetime(2026, 10, 8, 4, 20, tzinfo=UTC)
    antes = inicio - timedelta(days=7)
    depois = inicio + timedelta(minutes=27)
    _coleta(session, "siconfi-lote", "sucesso", depois)
    _coleta(session, "pol-senado", "sucesso", antes)
    _coleta(session, "pol-senado", "falha", depois, "HTTP 503 após 4 tentativas\nTraceback ...")
    _coleta(session, "pol-camara", "falha", depois, "HTTP 504 após 4 tentativas\nTraceback ...")
    situacao = {f["fonte"]: f for f in fontes.status(session, inicio)}
    assert situacao["siconfi-lote"]["atualizada_nesta_coleta"]
    senado = situacao["pol-senado"]
    assert not senado["atualizada_nesta_coleta"] and senado["disponivel"]
    assert senado["ultima_atualizacao"].startswith("2026-10-01")
    camara_ = situacao["pol-camara"]
    assert not camara_["disponivel"] and camara_["falha"] == "HTTP 504 após 4 tentativas"
    assert fontes.resumo(list(situacao.values())) == (
        "Fontes com falha: pol-camara (HTTP 504 após 4 tentativas; sem dado anterior: "
        "fonte indisponível nesta coleta); pol-senado (HTTP 503 após 4 tentativas; "
        "publicada com os dados de 2026-10-01)"
    )


def test_resumo_sem_falhas(session):
    _coleta(session, "pol-tse", "sucesso", datetime(2026, 10, 8, 5, tzinfo=UTC))
    assert fontes.resumo(fontes.status(session)) == "Fontes com falha: nenhuma"
