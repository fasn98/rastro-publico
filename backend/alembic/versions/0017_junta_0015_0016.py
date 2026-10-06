"""junta as cadeias 0015 (políticos) e 0016 (população IBGE)

Revision ID: 0017
Revises: 0015, 0016
Create Date: 2026-10-06

As duas migrações saíram do 0014 em branches paralelos. Uma revisão de junção (em vez de
mudar o down_revision do 0016) funciona também em bancos que já aplicaram o 0016 direto
sobre o 0014: o alembic aplica o que faltar dos dois lados.
"""

from collections.abc import Sequence

revision: str = "0017"
down_revision: str | Sequence[str] | None = ("0015", "0016")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
