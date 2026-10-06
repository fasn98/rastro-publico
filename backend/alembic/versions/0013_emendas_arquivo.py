"""emendas: origem (arquivo em lote ou API), linha, autor e ação; sem unicidade por código

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("pol_emenda_codigo_emenda_key", "pol_emenda", type_="unique")
    op.create_index("ix_pol_emenda_codigo_emenda", "pol_emenda", ["codigo_emenda"])
    op.add_column(
        "pol_emenda",
        sa.Column("fonte_dados", sa.String(10), nullable=False, server_default="api"),
    )
    op.add_column("pol_emenda", sa.Column("linha", sa.Integer()))
    op.add_column("pol_emenda", sa.Column("codigo_autor", sa.String(20)))
    op.add_column("pol_emenda", sa.Column("acao", sa.Text()))


def downgrade() -> None:
    for coluna in ("acao", "codigo_autor", "linha", "fonte_dados"):
        op.drop_column("pol_emenda", coluna)
    op.drop_index("ix_pol_emenda_codigo_emenda", table_name="pol_emenda")
    op.create_unique_constraint("pol_emenda_codigo_emenda_key", "pol_emenda", ["codigo_emenda"])
