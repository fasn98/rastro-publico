"""Banco de produção: sem credencial de desenvolvimento; usuário só de leitura da auditoria."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

import rastro.models  # noqa: F401  (registra as tabelas no metadata)
from rastro import seguranca


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://rastro:rastro@localhost:5432/rastro",
        "postgresql://rastro:rastro@ep-x.neon.tech/neondb",
        "postgresql://neondb_owner@ep-x.neon.tech/neondb",
    ],
)
def test_recusa_credencial_de_desenvolvimento_ou_sem_senha(url):
    with pytest.raises(seguranca.ErroSeguranca):
        seguranca.conferir_producao(url)


def test_aceita_credencial_propria():
    seguranca.conferir_producao("postgresql://neondb_owner:npg_Xy7kQ2@ep-x.neon.tech/neondb")


def test_senha_gerada_e_forte_e_unica():
    a, b = seguranca.gerar_senha(), seguranca.gerar_senha()
    assert a != b and len(a) >= 40


def test_usuario_de_auditoria_so_le_as_tabelas_da_auditoria(engine):
    url = seguranca.criar_usuario_auditoria(engine, senha="s3nha'com\\aspas")
    leitor = create_engine(url)
    try:
        with leitor.connect() as con:
            assert con.scalar(text("SELECT count(*) FROM resposta_bruta")) is not None
            with pytest.raises(DBAPIError, match="permission denied|read-only"):
                con.execute(text("SELECT count(*) FROM municipio"))
        with leitor.connect() as con, pytest.raises(DBAPIError, match="read-only|permission"):
            con.execute(text("DELETE FROM resposta_bruta"))
        # rodar de novo troca a senha (a antiga deixa de valer)
        nova = seguranca.criar_usuario_auditoria(engine)
        assert nova.password != url.password
        with create_engine(nova).connect() as con:
            con.execute(text("SELECT 1"))
    finally:
        leitor.dispose()
