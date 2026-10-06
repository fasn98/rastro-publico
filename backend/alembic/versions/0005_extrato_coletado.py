"""marcador de extrato coletado (para o indicador de transparência)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "extrato_coletado",
        sa.Column("cod_ibge", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("exercicio", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("itens", sa.Integer(), nullable=False),
        sa.Column(
            "lido_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    # extratos já gravados antes desta migração
    op.execute(
        "INSERT INTO extrato_coletado (cod_ibge, exercicio, itens) "
        "SELECT cod_ibge, exercicio, count(*) FROM entrega_siconfi GROUP BY 1, 2"
    )


def downgrade() -> None:
    op.drop_table("extrato_coletado")
