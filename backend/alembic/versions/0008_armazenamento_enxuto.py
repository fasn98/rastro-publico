"""armazenamento enxuto: demonstrativo -> respostas brutas e contagem de linhas gravadas

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("demonstrativo_siconfi", sa.Column("linhas_gravadas", sa.Integer()))
    op.create_table(
        "demonstrativo_resposta",
        sa.Column(
            "demonstrativo_id",
            sa.Integer(),
            sa.ForeignKey("demonstrativo_siconfi.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "resposta_id", sa.BigInteger(), sa.ForeignKey("resposta_bruta.id"), primary_key=True
        ),
    )
    op.create_index(
        "ix_demonstrativo_resposta_resposta_id", "demonstrativo_resposta", ["resposta_id"]
    )
    # dados existentes: a ligação sai das linhas já gravadas
    op.execute(
        "INSERT INTO demonstrativo_resposta (demonstrativo_id, resposta_id) "
        "SELECT DISTINCT demonstrativo_id, resposta_id FROM conta_demonstrativo "
        "WHERE resposta_id IS NOT NULL"
    )
    op.execute(
        "UPDATE demonstrativo_siconfi d SET linhas_gravadas = "
        "(SELECT count(*) FROM conta_demonstrativo c WHERE c.demonstrativo_id = d.id)"
    )


def downgrade() -> None:
    op.drop_table("demonstrativo_resposta")
    op.drop_column("demonstrativo_siconfi", "linhas_gravadas")
