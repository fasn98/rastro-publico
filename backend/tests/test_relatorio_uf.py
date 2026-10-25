"""Relatório de uma UF antes de liberar os políticos (scripts/relatorio_uf.py, só leitura).

Respostas reais do TSE gravadas em tests/fixtures/politicos (as mesmas de test_tse).
"""

import json
import sys
from pathlib import Path

import pytest
import respx
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_tse import AMOSTRA_IBGE
from test_tse import _mock as _mock_tse

from conftest import URL_TESTE
from rastro.coletores.arquivo import ArquivoBruto
from rastro.coletores.base import novo_cliente
from rastro.politicos import tse
from rastro.politicos.modelos import PolPolitico

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import relatorio_uf as r  # noqa: E402


@respx.mock
def test_contagens_sem_nomes(session, engine):
    _mock_tse()
    with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
        tse.coletar_eleitos(session, c, 2022, "SP", set())
        tse.coletar_eleitos(session, c, 2024, "SP", AMOSTRA_IBGE)
    rel = r.relatorio(session, "SP", com_fonte=False)
    gravados = session.scalars(select(PolPolitico).where(PolPolitico.uf == "SP")).all()
    assert rel["politicos"]["eleitos_tse"]["2024"]["prefeito"] == sum(
        1 for p in gravados if p.eleicao_ano == 2024 and p.cargo == "prefeito"
    )
    assert rel["politicos"]["segundo_turno_pendente"] == []
    assert rel["ultima_coleta"]["pol-tse"] == "ainda não coletada"
    saida = json.dumps(rel, ensure_ascii=False, default=str)
    assert gravados and not any(p.nome in saida for p in gravados)


def test_conexao_so_leitura_recusa_escrita():
    eng = create_engine(URL_TESTE, connect_args={"options": "-c default_transaction_read_only=on"})
    with Session(eng) as s, pytest.raises(DBAPIError, match="read-only"):
        s.execute(text("create temporary table x_teste (i int)"))
    eng.dispose()
