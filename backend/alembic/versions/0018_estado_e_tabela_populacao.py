"""estado do sistema e tabela de origem da população do IBGE (metodologia v1.1)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-09

- `estado`: chave/valor do que já foi aplicado ao banco (ex.: a versão do mapeamento de
  contas reconstruída do arquivo bruto), para não repetir trabalho a cada coleta.
- `populacao_ibge.tabela`: tabela do SIDRA de onde veio o número (6579 = estimativas;
  4709 = Censo 2022). As linhas existentes são da 6579.
- `nota_ranking.ano_populacao`: ano da população usada na faixa (v1.1: estimativa do IBGE).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "estado",
        sa.Column("chave", sa.String(80), primary_key=True),
        sa.Column("valor", sa.Text(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "populacao_ibge",
        sa.Column("tabela", sa.Integer(), nullable=False, server_default="6579"),
    )
    op.add_column("nota_ranking", sa.Column("ano_populacao", sa.Integer()))


def downgrade() -> None:
    op.drop_column("nota_ranking", "ano_populacao")
    op.drop_column("populacao_ibge", "tabela")
    op.drop_table("estado")
