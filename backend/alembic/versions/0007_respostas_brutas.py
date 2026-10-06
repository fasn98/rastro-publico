"""respostas brutas das fontes, para auditoria

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conteudo_bruto",
        sa.Column("sha256", sa.String(64), primary_key=True),
        sa.Column("tamanho", sa.BigInteger(), nullable=False),
        sa.Column("corpo_gzip", sa.LargeBinary(), nullable=False),
    )
    op.create_table(
        "resposta_bruta",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("coleta_id", sa.Integer(), sa.ForeignKey("coleta.id", ondelete="SET NULL")),
        sa.Column("fonte", sa.String(60)),
        sa.Column("metodo", sa.String(10), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("status_http", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(200)),
        sa.Column("recebida_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sha256_original", sa.String(64), nullable=False),
        sa.Column("tamanho_original", sa.BigInteger(), nullable=False),
        sa.Column(
            "sha256_gravado",
            sa.String(64),
            sa.ForeignKey("conteudo_bruto.sha256"),
            nullable=False,
        ),
        sa.Column("redacao", sa.Text()),
    )
    for coluna in ("coleta_id", "fonte", "recebida_em", "sha256_original", "sha256_gravado"):
        op.create_index(f"ix_resposta_bruta_{coluna}", "resposta_bruta", [coluna])


def downgrade() -> None:
    op.drop_table("resposta_bruta")
    op.drop_table("conteudo_bruto")
