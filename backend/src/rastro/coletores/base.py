import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from rastro.coletores.arquivo import (
    ArquivoBruto,
    Redator,
    coleta_atual,
    com_redacao,
    resposta_id,
)
from rastro.config import get_settings
from rastro.db import get_engine
from rastro.models import Coleta

log = logging.getLogger(__name__)


class LimiteDeTaxa:
    """Garante um intervalo mínimo entre o início de requisições consecutivas.

    Vale para todas as requisições do cliente, inclusive novas tentativas e páginas.
    """

    def __init__(self, req_por_segundo: float):
        self.intervalo = 1 / req_por_segundo if req_por_segundo > 0 else 0.0
        self._ultima = 0.0

    def __call__(self, _request: httpx.Request) -> None:
        if not self.intervalo:
            return
        espera = self._ultima + self.intervalo - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        self._ultima = time.monotonic()


def novo_cliente(
    req_por_segundo: float | None = None, arquivo: ArquivoBruto | None = None
) -> httpx.Client:
    """Cliente HTTP de todos os coletores: limite de taxa + arquivo de respostas brutas."""
    s = get_settings()
    limite = LimiteDeTaxa(s.req_por_segundo if req_por_segundo is None else req_por_segundo)
    if arquivo is None and s.arquivar_respostas:
        arquivo = ArquivoBruto(get_engine())
    return httpx.Client(
        timeout=s.http_timeout,
        headers={"User-Agent": s.user_agent, "Accept": "application/json"},
        follow_redirects=True,
        event_hooks={"request": [limite], "response": [arquivo] if arquivo else []},
    )


def _erro_transitorio(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


def get_json(client: httpx.Client, url: str, params: dict | None = None, *, decimal=False):
    """GET com novas tentativas para falhas de rede, 429 e 5xx.

    Com `decimal=True`, números com casas decimais viram `Decimal` (valores monetários).
    """
    return get_json_com_origem(client, url, params, decimal=decimal)[0]


def get_json_com_origem(
    client: httpx.Client,
    url: str,
    params: dict | None = None,
    *,
    decimal=False,
    redator: Redator | None = None,
) -> tuple[object, int | None]:
    """Como `get_json`, devolvendo também o id da resposta bruta arquivada (ou None).

    Com `redator`, a resposta é arquivada já sem os dados pessoais (ver `arquivo`); o
    coletor recebe o conteúdo completo e é responsável por não gravá-los nas tabelas.
    """

    @retry(
        retry=retry_if_exception(_erro_transitorio),
        stop=stop_after_attempt(get_settings().http_tentativas),
        wait=wait_exponential(multiplier=2, max=30),
        reraise=True,
    )
    def _get():
        resp = client.get(url, params=params, extensions=com_redacao(redator))
        resp.raise_for_status()
        dados = json.loads(resp.content, parse_float=Decimal) if decimal else resp.json()
        return dados, resposta_id(resp)

    return _get()


class ColetaParcial(Exception):
    """Coleta que gravou dados mas teve falhas em parte dos itens."""

    def __init__(self, registros: int, erros: list[str]):
        super().__init__(f"{len(erros)} falha(s)")
        self.registros = registros
        self.erros = erros


Coletor = Callable[[Session, httpx.Client], int]


def executar(session: Session, fonte: str, coletor: Coletor, client: httpx.Client) -> Coleta:
    """Roda um coletor e registra o resultado na tabela `coleta`."""
    coleta = Coleta(fonte=fonte, status="executando")
    session.add(coleta)
    session.commit()
    token = coleta_atual.set(coleta.id)
    try:
        coleta.registros = coletor(session, client)
        coleta.status = "sucesso"
    except ColetaParcial as exc:
        session.rollback()
        coleta.registros = exc.registros
        coleta.status = "parcial"
        coleta.erro = "\n".join(exc.erros)
        log.warning("Coleta %s parcial: %s", fonte, exc)
    except Exception as exc:
        session.rollback()
        coleta.status = "falha"
        coleta.erro = f"{type(exc).__name__}: {exc}"
        log.exception("Falha na coleta %s", fonte)
    finally:
        coleta_atual.reset(token)
    coleta.finalizada_em = datetime.now(UTC)
    session.add(coleta)
    session.commit()
    return coleta
