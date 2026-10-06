"""RREO e RGF do SICONFI

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "demonstrativo_siconfi",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cod_ibge", sa.Integer(), nullable=False),
        sa.Column("exercicio", sa.Integer(), nullable=False),
        sa.Column("demonstrativo", sa.String(30), nullable=False),
        sa.Column("periodicidade", sa.String(1), nullable=False),
        sa.Column("periodo", sa.Integer(), nullable=False),
        sa.Column("poder", sa.String(1)),
        sa.Column("instituicao", sa.String(200)),
        sa.Column("data_status", sa.DateTime(timezone=True)),
        sa.Column("linhas", sa.Integer(), nullable=False),
        sa.Column(
            "coletado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "cod_ibge",
            "exercicio",
            "demonstrativo",
            "periodicidade",
            "periodo",
            "poder",
            name="uq_demonstrativo_siconfi",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_demonstrativo_siconfi_cod_ibge", "demonstrativo_siconfi", ["cod_ibge"])

    op.create_table(
        "conta_demonstrativo",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "demonstrativo_id",
            sa.Integer(),
            sa.ForeignKey("demonstrativo_siconfi.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("anexo", sa.String(80), nullable=False),
        sa.Column("rotulo", sa.Text(), nullable=False),
        sa.Column("coluna", sa.Text(), nullable=False),
        sa.Column("cod_conta", sa.Text(), nullable=False),
        sa.Column("conta", sa.Text(), nullable=False),
        sa.Column("valor", sa.Numeric()),
    )
    op.create_index(
        "ix_conta_demonstrativo_demonstrativo_id", "conta_demonstrativo", ["demonstrativo_id"]
    )


def downgrade() -> None:
    op.drop_table("conta_demonstrativo")
    op.drop_table("demonstrativo_siconfi")
