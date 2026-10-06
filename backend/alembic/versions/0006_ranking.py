"""notas do Ranking Fiscal

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nota_ranking",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("versao", sa.String(20), nullable=False),
        sa.Column("hash_metodologia", sa.String(12), nullable=False),
        sa.Column("calculado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exercicios", sa.String(40), nullable=False),
        sa.Column("cod_ibge", sa.Integer(), nullable=False),
        sa.Column("uf", sa.String(2), nullable=False),
        sa.Column("populacao", sa.Integer()),
        sa.Column("faixa", sa.String(40)),
        sa.Column("nota", sa.Numeric(6, 4)),
        sa.Column("indicadores_faltantes", sa.Integer(), nullable=False),
        sa.Column("posicao_geral", sa.Integer()),
        sa.Column("posicao_faixa", sa.Integer()),
        sa.Column("componentes", JSONB(), nullable=False),
    )
    op.create_index("ix_nota_ranking_versao", "nota_ranking", ["versao"])
    op.create_index("ix_nota_ranking_cod_ibge", "nota_ranking", ["cod_ibge"])
    op.create_index("ix_nota_ranking_uf", "nota_ranking", ["uf"])


def downgrade() -> None:
    op.drop_table("nota_ranking")
