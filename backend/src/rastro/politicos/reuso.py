"""Quando a coleta dos políticos pode deixar de baixar de novo um arquivo (aprovado em 09/10/2026).

Vale para os anos fechados da Câmara (votos, presenças, cota e proposições de anos antes
do anterior ao corrente) e para as eleições do TSE que não são a corrente (2022 e 2024).
O arquivo só deixa de ser baixado se:

- já foi baixado com sucesso há menos de `IDADE_MAXIMA` (uma vez por semana ele é baixado
  de novo, para pegar retificações da fonte e, no TSE, as eleições suplementares);
- a resposta bruta daquele download está no arquivo (a chave estrangeira do SHA-256
  garante o conteúdo em `payload_bruto`), para a auditoria seguir funcionando; sem
  arquivamento de respostas, tudo é baixado de novo;
- no caso dos arquivos nacionais, os dados de TODAS as UFs pedidas vieram daquele download
  (uma UF nova na coleta faz o arquivo ser baixado de novo).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from rastro.models import RespostaBruta
from rastro.politicos.modelos import (
    PolDespesaCota,
    PolPolitico,
    PolPresenca,
    PolVotacao,
)

IDADE_MAXIMA = timedelta(days=7)


def ano_fechado(ano: int, hoje: datetime | None = None) -> bool:
    """Anos antes do anterior ao corrente (em 2026: 2023 e 2024)."""
    return ano < (hoje or datetime.now(UTC)).year - 1


def _limite(agora: datetime | None) -> datetime:
    return (agora or datetime.now(UTC)) - IDADE_MAXIMA


def url_recente(session: Session, url: str, agora: datetime | None = None) -> bool:
    """A URL exata teve resposta 200 arquivada há menos de IDADE_MAXIMA."""
    return (
        session.scalar(
            select(RespostaBruta.id)
            .where(
                RespostaBruta.url == url,
                RespostaBruta.status_http == 200,
                RespostaBruta.recebido_em >= _limite(agora),
            )
            .limit(1)
        )
        is not None
    )


_TABELAS_CAMARA = {
    "votos": (PolVotacao, lambda: extract("year", PolVotacao.data)),
    "presencas": (PolPresenca, lambda: extract("year", PolPresenca.data_hora_inicio)),
    "cota": (PolDespesaCota, lambda: PolDespesaCota.ano),
}


def ufs_com_arquivo_recente(
    session: Session, tipo: str, ano: int, agora: datetime | None = None
) -> set[str]:
    """UFs cujos deputados têm linhas do ano vindas de um download recente e arquivado."""
    modelo, coluna_ano = _TABELAS_CAMARA[tipo]
    return set(
        session.scalars(
            select(PolPolitico.uf)
            .distinct()
            .join(modelo, modelo.politico_id == PolPolitico.id)
            .join(RespostaBruta, RespostaBruta.id == modelo.resposta_id)
            .where(
                PolPolitico.fonte == "camara",
                coluna_ano() == ano,
                RespostaBruta.recebido_em >= _limite(agora),
            )
        )
    )


def tse_recente(session: Session, ano: int, uf: str, agora: datetime | None = None) -> bool:
    """Os eleitos do TSE de `ano` na UF vieram de um download recente e arquivado."""
    return (
        session.scalar(
            select(PolPolitico.id)
            .join(RespostaBruta, RespostaBruta.id == PolPolitico.resposta_id)
            .where(
                PolPolitico.fonte == "tse",
                PolPolitico.eleicao_ano == ano,
                PolPolitico.uf == uf,
                RespostaBruta.recebido_em >= _limite(agora),
            )
            .limit(1)
        )
        is not None
    )
