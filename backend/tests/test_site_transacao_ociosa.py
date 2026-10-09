"""A exportação não pode segurar transação aberta e ociosa.

Em produção (Neon/Replit), o banco encerra a conexão que fica "idle in transaction" além
de `idle_in_transaction_session_timeout`. Em 09/10/2026 (execução 6pfw6), a exportação
abria uma transação na sessão dela, passava minutos chamando a API interna e, ao voltar a
consultar (`_catalogos`), recebia IdleInTransactionSessionTimeout.

Aqui o mesmo limite é ligado nas conexões do teste (1 s), e cada chamada à API interna
demora um pouco, como numa exportação grande. Mesmos dados reais gravados do test_site.
"""

import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from test_site import HOJE, banco, coletado  # noqa: F401 (fixtures)

from conftest import URL_TESTE
from rastro import db, site

LIMITE_MS = 1000


@pytest.fixture
def banco_com_limite(monkeypatch):
    """Banco de teste com idle_in_transaction_session_timeout baixo, como em produção."""
    sep = "&" if "?" in URL_TESTE else "?"
    url = f"{URL_TESTE}{sep}options=-c%20idle_in_transaction_session_timeout%3D{LIMITE_MS}"
    engine = create_engine(url, pool_pre_ping=True)
    fabrica = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    monkeypatch.setattr(db, "get_sessionmaker", lambda: fabrica)
    with engine.connect() as con:
        assert con.exec_driver_sql("SHOW idle_in_transaction_session_timeout").scalar() == "1s"
    yield engine
    engine.dispose()


@pytest.fixture
def api_lenta(monkeypatch):
    """Chamadas à API interna lentas onde a exportação fica sem consultar a própria sessão:
    o laço dos municípios (antes de `_catalogos`) e a primeira página de político (entre
    usos do `_Arquivados`). Em produção, esses intervalos somam minutos."""
    original = site._cliente

    class Lento:
        def __init__(self, cliente):
            self.cliente = cliente
            self.politico = False

        def get(self, url):
            if url.startswith("/api/municipios/"):
                time.sleep(0.3)
            elif url.startswith("/api/politicos/") and not self.politico:
                self.politico = True
                time.sleep(LIMITE_MS / 1000 + 0.5)
            return self.cliente.get(url)

    monkeypatch.setattr(site, "_cliente", lambda session: Lento(original(session)))


def test_exportacao_sem_transacao_ociosa(coletado, banco_com_limite, api_lenta, tmp_path):  # noqa: F811
    """Como na coleta de produção: a exportação abre a própria sessão (session=None)."""
    coletado.commit()
    manifesto = site.exportar(tmp_path / "dados", "SP", session=None, hoje=HOJE)
    assert manifesto["contagens"]["municipios"] == 2
    assert manifesto["contagens"]["politicos"] > 0
