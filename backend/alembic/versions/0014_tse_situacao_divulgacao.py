"""pol_politico: situação da candidatura e data de divulgação (TSE)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pol_politico", sa.Column("situacao_candidatura", sa.String(80)))
    op.add_column("pol_politico", sa.Column("data_divulgacao", sa.Date()))


def downgrade() -> None:
    op.drop_column("pol_politico", "data_divulgacao")
    op.drop_column("pol_politico", "situacao_candidatura")
