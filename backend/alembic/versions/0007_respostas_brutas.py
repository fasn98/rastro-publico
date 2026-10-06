"""arquivo de respostas brutas (auditoria) e origem de cada registro

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

TABELAS_COM_ORIGEM = ("municipio", "ente_siconfi", "entrega_siconfi", "conta_demonstrativo")


def upgrade() -> None:
    op.create_table(
        "payload_bruto",
        sa.Column("sha256", sa.String(64), primary_key=True),
        sa.Column("tamanho", sa.Integer(), nullable=False),
        sa.Column("compressao", sa.String(10), nullable=False),
        sa.Column("conteudo", sa.LargeBinary(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "resposta_bruta",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("coleta_id", sa.Integer(), sa.ForeignKey("coleta.id")),
        sa.Column("metodo", sa.String(10), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("status_http", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(120)),
        sa.Column("recebido_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duracao_ms", sa.Integer()),
        sa.Column("sha256", sa.String(64), sa.ForeignKey("payload_bruto.sha256"), nullable=False),
        sa.Column("tamanho", sa.Integer(), nullable=False),
    )
    op.create_index("ix_resposta_bruta_coleta_id", "resposta_bruta", ["coleta_id"])
    op.create_index("ix_resposta_bruta_sha256", "resposta_bruta", ["sha256"])
    for tabela in TABELAS_COM_ORIGEM:
        op.add_column(
            tabela,
            sa.Column("resposta_id", sa.BigInteger(), sa.ForeignKey("resposta_bruta.id")),
        )
        op.create_index(f"ix_{tabela}_resposta_id", tabela, ["resposta_id"])


def downgrade() -> None:
    for tabela in TABELAS_COM_ORIGEM:
        op.drop_column(tabela, "resposta_id")
    op.drop_table("resposta_bruta")
    op.drop_table("payload_bruto")
