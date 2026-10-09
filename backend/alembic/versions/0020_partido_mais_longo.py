"""pol_politico.partido: 30 -> 120 caracteres

Quem saiu do exercício guarda todos os partidos pelos quais passou na legislatura ("UNIÃO /
REPUBLICANOS / SOLIDARIEDADE", 36 caracteres, deputado do CE). Em SP cabia em 30; na lista
nacional da legislatura 57 (648 deputados, 09/10/2026), não.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("pol_politico", "partido", type_=sa.String(120), existing_type=sa.String(30))


def downgrade() -> None:
    op.alter_column("pol_politico", "partido", type_=sa.String(30), existing_type=sa.String(120))
