"""populacao_ibge: população residente estimada do IBGE (SIDRA, tabela 6579)

Revision ID: 0016
Revises: 0014
Create Date: 2026-10-06

Numerada 0016 porque o 0015 está em uso no branch feature/politicos-4: quem entrar no
main por último ajusta o down_revision para manter uma cadeia só.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "populacao_ibge",
        sa.Column("cod_ibge", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("ano", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("populacao", sa.Integer(), nullable=False),
        sa.Column("resposta_id", sa.BigInteger(), sa.ForeignKey("resposta_bruta.id")),
    )
    op.create_index("ix_populacao_ibge_resposta_id", "populacao_ibge", ["resposta_id"])


def downgrade() -> None:
    op.drop_index("ix_populacao_ibge_resposta_id", "populacao_ibge")
    op.drop_table("populacao_ibge")
