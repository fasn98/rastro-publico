"""Situação de cada fonte na coleta: o que foi atualizado, o que falhou e desde quando.

A falha de uma fonte não impede a publicação das demais (`scripts/coleta_sp.sh`):

- a fonte é tentada de novo, com espera progressiva, se o erro for transitório (rede,
  429, 5xx): `executar_com_esperas`;
- se continuar falhando, o site é publicado com os dados anteriores dela, que continuam
  no banco; o manifesto (`fontes`) e a página "Status das fontes" dizem que ela não foi
  atualizada nesta coleta e a data da última atualização bem-sucedida;
- se ela nunca foi coletada com sucesso, as seções dela aparecem como "fonte
  indisponível nesta coleta", e a verificação antes de publicar aceita esse caso.

A coleta termina com erro só quando algo crítico falha: banco, migrações, verificação de
integridade do arquivo bruto ou o envio ao GitHub.
"""

import logging
import time
from collections.abc import Callable
from datetime import datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rastro.coletores.base import Coletor, executar
from rastro.config import get_settings
from rastro.models import Coleta

log = logging.getLogger(__name__)

NOMES = {
    "ibge-municipios": "IBGE: municípios",
    "ibge-populacao": "IBGE: população",
    "siconfi-entes": "Tesouro (SICONFI): cadastro de entes",
    "siconfi-lote": "Tesouro (SICONFI): RREO e RGF",
    "pol-camara": "Câmara dos Deputados",
    "pol-senado": "Senado Federal",
    "pol-emendas": "Portal da Transparência: emendas",
    "pol-tse": "TSE: eleitos",
}
# fontes cuja falha muda o número de políticos do site
FONTES_POLITICOS = ("pol-camara", "pol-senado", "pol-tse")
OK = ("sucesso", "parcial")


def transitorio(exc: BaseException | None) -> bool:
    """Erro que pode passar sozinho: rede, tempo esgotado, 429 ou 5xx."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


def descrever_erro(exc: BaseException | None) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__ if exc else "erro"


def esperas_configuradas() -> list[float]:
    texto = get_settings().fonte_esperas
    return [float(x) for x in texto.split(",") if x.strip()]


def executar_com_esperas(
    session: Session,
    fonte: str,
    coletor: Coletor,
    novo_cliente: Callable[[], httpx.Client],
    esperas: list[float] | None = None,
    dormir: Callable[[float], None] = time.sleep,
) -> Coleta:
    """Roda a fonte; em erro transitório, tenta de novo após cada espera (segundos).

    Cada rodada fica registrada na tabela `coleta`. Na última falha, o erro gravado começa
    com o resumo (ex.: "HTTP 504 após 4 tentativas"), seguido do traceback completo.
    """
    esperas = esperas_configuradas() if esperas is None else esperas
    tentativas = 0
    while True:
        tentativas += 1
        with novo_cliente() as client:
            coleta = executar(session, fonte, coletor, client)
        exc = getattr(coleta, "excecao", None)
        if coleta.status != "falha" or not transitorio(exc) or tentativas > len(esperas):
            break
        espera = esperas[tentativas - 1]
        log.warning(
            "%s: %s na tentativa %d; nova tentativa em %.0f s",
            fonte, descrever_erro(exc), tentativas, espera,
        )  # fmt: skip
        dormir(espera)
    if coleta.status == "falha":
        resumo = f"{descrever_erro(exc)} após {tentativas} tentativa{'s' if tentativas > 1 else ''}"
        coleta.erro = f"{resumo}\n{coleta.erro or ''}"
        session.commit()
    return coleta


def status(session: Session, desde: datetime | None = None) -> list[dict]:
    """Situação de cada fonte já tentada ao menos uma vez.

    `desde`: início da coleta em andamento. Uma fonte "foi atualizada nesta coleta" se
    teve sucesso (total ou parcial) desde então; sem `desde`, vale a última tentativa.
    """
    saida = []
    for fonte in session.scalars(select(Coleta.fonte).distinct().order_by(Coleta.fonte)):
        ultima_ok = session.scalar(
            select(func.max(Coleta.finalizada_em)).where(
                Coleta.fonte == fonte, Coleta.status.in_(OK)
            )
        )
        ultima = session.scalars(
            select(Coleta)
            .where(Coleta.fonte == fonte, Coleta.status != "executando")
            .order_by(Coleta.iniciada_em.desc(), Coleta.id.desc())
        ).first()
        if ultima is None:
            continue
        if desde is not None:
            tentou = ultima.iniciada_em >= desde
            atualizada = ultima_ok is not None and ultima_ok >= desde
        else:
            tentou, atualizada = True, ultima.status in OK
        saida.append(
            {
                "fonte": fonte,
                "nome": NOMES.get(fonte, fonte),
                "ultima_atualizacao": ultima_ok.isoformat() if ultima_ok else None,
                "tentada_nesta_coleta": tentou,
                "atualizada_nesta_coleta": atualizada,
                "disponivel": ultima_ok is not None,
                # primeira linha do erro: o resumo (o traceback fica no banco e no log)
                "falha": (ultima.erro or "").splitlines()[0][:200]
                if tentou and not atualizada and ultima.erro
                else None,
            }
        )
    return saida


def com_falha(fontes: list[dict]) -> list[dict]:
    return [f for f in fontes if f["tentada_nesta_coleta"] and not f["atualizada_nesta_coleta"]]


def resumo(fontes: list[dict]) -> str:
    falhas = com_falha(fontes)
    if not falhas:
        return "Fontes com falha: nenhuma"
    partes = []
    for f in falhas:
        detalhe = f["falha"] or "falha"
        if f["disponivel"]:
            detalhe += f"; publicada com os dados de {f['ultima_atualizacao'][:10]}"
        else:
            detalhe += "; sem dado anterior: fonte indisponível nesta coleta"
        partes.append(f"{f['fonte']} ({detalhe})")
    return "Fontes com falha: " + "; ".join(partes)
