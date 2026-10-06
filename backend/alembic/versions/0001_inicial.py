"""estrutura inicial: municipio, ente_siconfi, coleta

Revision ID: 0001
Revises:
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # usada na busca de municípios por nome sem acento
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    op.create_table(
        "municipio",
        sa.Column("cod_ibge", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("uf", sa.String(2), nullable=False),
        sa.Column("regiao", sa.String(2), nullable=False),
        sa.Column("microrregiao", sa.String(120)),
        sa.Column("mesorregiao", sa.String(120)),
        sa.Column("regiao_imediata", sa.String(120)),
        sa.Column("regiao_intermediaria", sa.String(120)),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_municipio_uf", "municipio", ["uf"])

    op.create_table(
        "ente_siconfi",
        sa.Column("cod_ibge", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("esfera", sa.String(1), nullable=False),
        sa.Column("uf", sa.String(2)),
        sa.Column("regiao", sa.String(2), nullable=False),
        sa.Column("capital", sa.Boolean(), nullable=False),
        sa.Column("populacao", sa.Integer()),
        sa.Column("cnpj", sa.String(14)),
        sa.Column("exercicio", sa.Integer(), nullable=False),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_ente_siconfi_esfera", "ente_siconfi", ["esfera"])
    op.create_index("ix_ente_siconfi_uf", "ente_siconfi", ["uf"])

    op.create_table(
        "coleta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fonte", sa.String(60), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("registros", sa.Integer()),
        sa.Column("erro", sa.Text()),
        sa.Column(
            "iniciada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finalizada_em", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_coleta_fonte", "coleta", ["fonte"])


def downgrade() -> None:
    op.drop_table("coleta")
    op.drop_table("ente_siconfi")
    op.drop_table("municipio")
