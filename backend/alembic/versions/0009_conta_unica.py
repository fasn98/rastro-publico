"""unicidade da célula em conta_demonstrativo

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUNAS = ["demonstrativo_id", "anexo", "rotulo", "cod_conta", "conta", "coluna"]


def upgrade() -> None:
    # remove duplicatas eventuais (fica a de menor id) antes de criar a restrição
    op.execute(
        "DELETE FROM conta_demonstrativo a USING conta_demonstrativo b "
        "WHERE a.id > b.id AND " + " AND ".join(f"a.{c} = b.{c}" for c in COLUNAS)
    )
    op.create_unique_constraint("uq_conta_demonstrativo", "conta_demonstrativo", COLUNAS)


def downgrade() -> None:
    op.drop_constraint("uq_conta_demonstrativo", "conta_demonstrativo")
