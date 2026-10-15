"""pol_coleta_uf: resultado de cada coleta dos políticos por UF (portão de políticos)

A tabela `coleta` não tem UF, e a Câmara e as emendas cobrem várias UFs numa execução só.
Aprovado pelo Fabio em 15/10/2026.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pol_coleta_uf",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("coleta_id", sa.Integer(), sa.ForeignKey("coleta.id"), nullable=False),
        sa.Column("fonte", sa.String(60), nullable=False),
        sa.Column("uf", sa.String(2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("motivo", sa.Text()),
        sa.Column(
            "registrada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_pol_coleta_uf_coleta_id", "pol_coleta_uf", ["coleta_id"])
    op.create_index("ix_pol_coleta_uf_fonte_uf", "pol_coleta_uf", ["fonte", "uf", "id"])


def downgrade() -> None:
    op.drop_index("ix_pol_coleta_uf_fonte_uf", table_name="pol_coleta_uf")
    op.drop_index("ix_pol_coleta_uf_coleta_id", table_name="pol_coleta_uf")
    op.drop_table("pol_coleta_uf")
