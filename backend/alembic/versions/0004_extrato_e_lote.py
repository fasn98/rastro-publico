"""extrato de entregas e coleta em lote retomável

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entrega_siconfi",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cod_ibge", sa.Integer(), nullable=False),
        sa.Column("exercicio", sa.Integer(), nullable=False),
        sa.Column("entregavel", sa.String(120), nullable=False),
        sa.Column("periodicidade", sa.String(1)),
        sa.Column("periodo", sa.Integer()),
        sa.Column("instituicao", sa.String(200)),
        sa.Column("status_relatorio", sa.String(4)),
        sa.Column("tipo_relatorio", sa.String(4)),
        sa.Column("forma_envio", sa.String(20)),
        sa.Column("data_status", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_entrega_siconfi_cod_ibge", "entrega_siconfi", ["cod_ibge"])

    op.create_table(
        "lote_coleta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chave", sa.String(200), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finalizado_em", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_lote_coleta_chave", "lote_coleta", ["chave"])

    op.create_table(
        "item_lote",
        sa.Column("lote_id", sa.Integer(), sa.ForeignKey("lote_coleta.id"), primary_key=True),
        sa.Column("cod_ibge", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("exercicio", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("linhas", sa.Integer()),
        sa.Column("erro", sa.Text()),
        sa.Column("tentativas", sa.Integer(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("item_lote")
    op.drop_table("lote_coleta")
    op.drop_table("entrega_siconfi")
