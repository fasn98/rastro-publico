"""LGPD: CPF citado em texto livre (só dados; nenhuma mudança de esquema)

Ementas de denúncias da Câmara trazem o CPF da pessoa denunciada ("inscrito no CPF sob o
n° ..."); a descrição de uma votação de 2023 lista pessoas com o CPF; o nome de fornecedor
MEI da cota traz o CPF com pontuação parcial, que a regra anterior não pegava. Desde
15/10/2026 a coleta troca o número por "[CPF removido]" no banco e no arquivo bruto. Esta
migração faz o mesmo, uma vez, no que já estava gravado (a mesma redação do
`rastro redigir-respostas`):

- banco: `pol_proposicao.ementa` e `.autoria`, `pol_votacao.descricao`,
  `pol_despesa_cota.fornecedor`;
- arquivo bruto: respostas de /proposicoes (Câmara), /processo (Senado) e
  votacoes-{ano}.csv (Câmara) com CPF no texto são regravadas redigidas, com o SHA-256 do
  original, o da versão redigida e os campos alterados (`redigir_arquivadas`); a cota já
  redigida antes é redigida de novo, mantendo o SHA-256 da fonte (`reaplicar_redacao`).
  Resposta sem CPF fica como está.

Não há volta: o original com o CPF não é guardado em lugar nenhum.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-15
"""

import logging
from collections.abc import Sequence

from alembic import op
from sqlalchemy.orm import Session

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    from rastro.coletores.redacao import reaplicar_redacao, redigir_arquivadas
    from rastro.politicos import lgpd

    session = Session(bind=op.get_bind())
    linhas = lgpd.limpar_cpf_nas_tabelas(session)
    respostas = redigir_arquivadas(session, lgpd.REGRAS)
    respostas += reaplicar_redacao(session, lgpd.REDIGIR_DE_NOVO)
    log.info(
        "0022: %d linha(s) do banco e %d resposta(s) arquivada(s) sem o CPF citado no texto",
        linhas,
        respostas,
    )


def downgrade() -> None:
    pass  # o CPF removido não volta
