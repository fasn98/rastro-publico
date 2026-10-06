"""RGF separado por instituição

Até a 0002, as linhas de instituições do mesmo poder (ex.: Câmara e Tribunal de Contas
do Município) eram gravadas juntas e não dava para separá-las. Os demonstrativos
existentes são apagados; rode `rastro siconfi-demonstrativos` de novo para recoletar.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM demonstrativo_siconfi")
    op.drop_constraint("uq_demonstrativo_siconfi", "demonstrativo_siconfi")
    op.create_unique_constraint(
        "uq_demonstrativo_siconfi",
        "demonstrativo_siconfi",
        ["cod_ibge", "exercicio", "demonstrativo", "periodicidade", "periodo", "poder",
         "instituicao"],
        postgresql_nulls_not_distinct=True,
    )  # fmt: skip


def downgrade() -> None:
    op.execute("DELETE FROM demonstrativo_siconfi")
    op.drop_constraint("uq_demonstrativo_siconfi", "demonstrativo_siconfi")
    op.create_unique_constraint(
        "uq_demonstrativo_siconfi",
        "demonstrativo_siconfi",
        ["cod_ibge", "exercicio", "demonstrativo", "periodicidade", "periodo", "poder"],
        postgresql_nulls_not_distinct=True,
    )
