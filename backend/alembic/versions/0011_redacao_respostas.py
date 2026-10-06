"""redação LGPD no arquivo de respostas brutas

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("resposta_bruta", sa.Column("sha256_original", sa.String(64)))
    op.add_column("resposta_bruta", sa.Column("tamanho_original", sa.BigInteger()))
    op.add_column("resposta_bruta", sa.Column("campos_removidos", JSONB()))
    op.add_column("resposta_bruta", sa.Column("redacao", sa.Text()))
    op.create_index("ix_resposta_bruta_sha256_original", "resposta_bruta", ["sha256_original"])


def downgrade() -> None:
    op.drop_index("ix_resposta_bruta_sha256_original", table_name="resposta_bruta")
    for coluna in ("redacao", "campos_removidos", "tamanho_original", "sha256_original"):
        op.drop_column("resposta_bruta", coluna)
