import logging
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from rastro.config import get_settings
from rastro.models import Coleta

log = logging.getLogger(__name__)


def novo_cliente() -> httpx.Client:
    s = get_settings()
    return httpx.Client(
        timeout=s.http_timeout,
        headers={"User-Agent": s.user_agent, "Accept": "application/json"},
        follow_redirects=True,
    )


def _erro_transitorio(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


def get_json(client: httpx.Client, url: str, params: dict | None = None):
    """GET com novas tentativas para falhas de rede, 429 e 5xx."""

    @retry(
        retry=retry_if_exception(_erro_transitorio),
        stop=stop_after_attempt(get_settings().http_tentativas),
        wait=wait_exponential(multiplier=2, max=30),
        reraise=True,
    )
    def _get():
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    return _get()


Coletor = Callable[[Session, httpx.Client], int]


def executar(session: Session, fonte: str, coletor: Coletor, client: httpx.Client) -> Coleta:
    """Roda um coletor e registra o resultado na tabela `coleta`."""
    coleta = Coleta(fonte=fonte, status="executando")
    session.add(coleta)
    session.commit()
    try:
        coleta.registros = coletor(session, client)
        coleta.status = "sucesso"
    except Exception as exc:
        session.rollback()
        coleta.status = "falha"
        coleta.erro = f"{type(exc).__name__}: {exc}"
        log.exception("Falha na coleta %s", fonte)
    coleta.finalizada_em = datetime.now(UTC)
    session.add(coleta)
    session.commit()
    return coleta
