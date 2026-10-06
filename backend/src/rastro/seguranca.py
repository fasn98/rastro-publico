"""Cuidados com o banco de produção.

- `conferir_producao`: recusa subir em produção com a credencial de desenvolvimento
  (`rastro:rastro`) ou sem senha. Chamado por `scripts/replit.sh` antes de cada papel.
- `criar_usuario_auditoria`: cria (ou troca a senha de) um usuário só de leitura para a
  API de auditoria, com senha forte gerada aqui. Se o provedor não deixar criar usuários,
  diz isso claramente: o guia de deploy registra esse caso como risco aceito.
"""

import secrets

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError

USUARIO_AUDITORIA = "rastro_auditoria"
# as únicas tabelas que a API de auditoria lê
TABELAS_AUDITORIA = (
    "resposta_bruta",
    "payload_bruto",
    "demonstrativo_resposta",
    "conta_demonstrativo",
)
CREDENCIAIS_DEV = {("rastro", "rastro")}


class ErroSeguranca(RuntimeError):
    pass


def conferir_producao(url: str) -> None:
    u = make_url(url)
    if not u.password:
        raise ErroSeguranca("a string de conexão de produção não tem senha")
    if (u.username, u.password) in CREDENCIAIS_DEV:
        raise ErroSeguranca(
            "a string de conexão usa a credencial de desenvolvimento (rastro:rastro); "
            "use a do banco de produção, com senha própria"
        )


def gerar_senha() -> str:
    # 32 bytes aleatórios (256 bits), em caracteres seguros para URL
    return secrets.token_urlsafe(32)


def criar_usuario_auditoria(engine, senha: str | None = None) -> URL:
    """Cria o usuário só de leitura e devolve a string de conexão dele.

    Levanta ErroSeguranca se o banco não permitir (ex.: dono sem CREATEROLE).
    """
    senha = senha or gerar_senha()
    try:
        with engine.begin() as con:
            existe = con.scalar(
                text("SELECT 1 FROM pg_roles WHERE rolname = :n"), {"n": USUARIO_AUDITORIA}
            )
            # a senha vai como literal escapado pelo próprio PostgreSQL (quote_literal)
            literal = con.scalar(text("SELECT quote_literal(:s)"), {"s": senha})
            acao = "ALTER" if existe else "CREATE"
            con.execute(text(f"{acao} ROLE {USUARIO_AUDITORIA} WITH LOGIN PASSWORD {literal}"))
            con.execute(
                text(f"ALTER ROLE {USUARIO_AUDITORIA} SET default_transaction_read_only = on")
            )
            banco = con.scalar(text("SELECT current_database()"))
            con.execute(text(f'GRANT CONNECT ON DATABASE "{banco}" TO {USUARIO_AUDITORIA}'))
            con.execute(text(f"GRANT USAGE ON SCHEMA public TO {USUARIO_AUDITORIA}"))
            con.execute(
                text(f"GRANT SELECT ON {', '.join(TABELAS_AUDITORIA)} TO {USUARIO_AUDITORIA}")
            )
    except DBAPIError as exc:
        raise ErroSeguranca(
            f"o banco não permitiu criar o usuário só de leitura: {exc.orig}"
        ) from exc
    return engine.url.set(username=USUARIO_AUDITORIA, password=senha)
