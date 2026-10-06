import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from rastro.db import Base

FIXTURES = Path(__file__).parent / "fixtures"
URL_TESTE = os.environ.get(
    "RASTRO_TEST_DATABASE_URL", "postgresql+psycopg://rastro:rastro@localhost:5432/rastro_teste"
)


def carregar(nome: str):
    return json.loads((FIXTURES / nome).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def configuracao_rapida(monkeypatch):
    """Sem pausas entre requisições nem novas tentativas durante os testes."""
    from rastro.config import get_settings

    monkeypatch.setenv("RASTRO_SICONFI_INTERVALO", "0")
    monkeypatch.setenv("RASTRO_HTTP_TENTATIVAS", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(URL_TESTE)
    try:
        with eng.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
    except OperationalError:
        pytest.skip(f"PostgreSQL de teste indisponível em {URL_TESTE}")
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session(engine):
    Sessao = sessionmaker(bind=engine, expire_on_commit=False)
    with Sessao() as s:
        yield s
    with engine.begin() as conn:
        for tabela in reversed(Base.metadata.sorted_tables):
            conn.execute(tabela.delete())
