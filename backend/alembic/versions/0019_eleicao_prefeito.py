"""pol_eleicao_prefeito: eleições de prefeito (ordinária e suplementares) com prefeito e
vice eleitos, do TSE (ADR-0018)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pol_eleicao_prefeito",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uf", sa.String(2), nullable=False),
        sa.Column("cod_ibge", sa.Integer(), nullable=False),
        sa.Column("eleicao_ano", sa.Integer(), nullable=False),
        sa.Column("mandato_inicio", sa.Integer(), nullable=False),
        sa.Column("mandato_fim", sa.Integer(), nullable=False),
        sa.Column("cd_eleicao", sa.String(10), nullable=False),
        sa.Column("ds_eleicao", sa.Text(), nullable=False),
        sa.Column("data_eleicao", sa.Date(), nullable=False),
        sa.Column("suplementar", sa.Boolean(), nullable=False),
        sa.Column("turno", sa.Integer(), nullable=False),
        sa.Column("prefeito", sa.String(120)),
        sa.Column("prefeito_partido", sa.String(30)),
        sa.Column("vice", sa.String(120)),
        sa.Column("vice_partido", sa.String(30)),
        sa.Column("data_divulgacao", sa.Date()),
        sa.Column("url_fonte", sa.Text(), nullable=False),
        sa.Column("resposta_id", sa.BigInteger(), sa.ForeignKey("resposta_bruta.id")),
        sa.UniqueConstraint("cod_ibge", "cd_eleicao", name="uq_pol_eleicao_prefeito"),
    )
    op.create_index("ix_pol_eleicao_prefeito_cod_ibge", "pol_eleicao_prefeito", ["cod_ibge"])
    op.create_index("ix_pol_eleicao_prefeito_resposta_id", "pol_eleicao_prefeito", ["resposta_id"])


def downgrade() -> None:
    op.drop_table("pol_eleicao_prefeito")
