"""pol_emenda.uf_destino: UF da coluna "UF" do arquivo de emendas do Portal

Permite contar, por UF, quantas emendas do período não informam o município de destino
(localidade "MÚLTIPLO" ou o estado inteiro), para a nota das páginas do município e da UF.
Pedido do Fabio em 26/10/2026.

A coluna fica vazia até a próxima coleta de emendas, que regrava todas as linhas do
arquivo em lote.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pol_emenda", sa.Column("uf_destino", sa.String(2)))
    op.create_index("ix_pol_emenda_uf_destino", "pol_emenda", ["uf_destino"])


def downgrade() -> None:
    op.drop_index("ix_pol_emenda_uf_destino", table_name="pol_emenda")
    op.drop_column("pol_emenda", "uf_destino")
