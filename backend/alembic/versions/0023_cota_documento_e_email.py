"""LGPD: CPF no número do documento e e-mail no nome do fornecedor da cota (só dados)

Decisão do Fabio em 15/10/2026, depois da varredura de LGPD:
- número do documento fiscal (`txtNumero`): sai só o que é CPF (11 dígitos, com ou sem
  pontuação, com dígito verificador válido), trocado por "[CPF removido]"; os demais
  números de documento ficam;
- e-mail no nome do fornecedor: trocado por "[e-mail removido]", como o CPF no nome de
  fornecedor MEI.

A coleta aplica as regras desde então. Esta migração faz o mesmo, uma vez, no que já
estava gravado: `pol_despesa_cota.numero_documento` e `.fornecedor`, e as respostas
arquivadas da cota (já redigidas antes), que são redigidas de novo mantendo o SHA-256 da
fonte e acrescentando os campos alterados (`reaplicar_redacao`). A mesma limpeza roda com
`rastro redigir-respostas`.

Não há volta: o valor removido não é guardado em lugar nenhum.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-15
"""

import logging
from collections.abc import Sequence

from alembic import op
from sqlalchemy.orm import Session

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    from rastro.coletores.redacao import reaplicar_redacao
    from rastro.politicos import lgpd

    session = Session(bind=op.get_bind())
    linhas = lgpd.limpar_cpf_nas_tabelas(session)
    respostas = reaplicar_redacao(session, lgpd.REDIGIR_DE_NOVO)
    log.info(
        "0023: %d linha(s) do banco e %d resposta(s) arquivada(s) da cota sem CPF no número "
        "do documento nem e-mail no nome do fornecedor",
        linhas,
        respostas,
    )


def downgrade() -> None:
    pass  # o valor removido não volta
