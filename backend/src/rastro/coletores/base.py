import gzip
import hashlib
import json
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy import Engine, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from rastro.config import get_settings
from rastro.models import Coleta, ConteudoBruto, RespostaBruta

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


def novo_cliente(req_por_segundo: float | None = None) -> httpx.Client:
    s = get_settings()
    limite = LimiteDeTaxa(s.req_por_segundo if req_por_segundo is None else req_por_segundo)
    return httpx.Client(
        timeout=s.http_timeout,
        headers={"User-Agent": s.user_agent, "Accept": "application/json"},
        follow_redirects=True,
        event_hooks={"request": [limite]},
    )


def _erro_transitorio(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


# Função que recebe o corpo original e devolve (corpo a gravar, descrição do que foi removido).
# Usada quando a resposta traz dados pessoais que não podem ser armazenados (LGPD).
Redator = Callable[[bytes], tuple[bytes, str]]

_EXT_REDATOR = "rastro_redator"
_EXT_RESPOSTA_ID = "rastro_resposta_id"


class GravadorRespostas:
    """Grava cada resposta HTTP recebida em `resposta_bruta`/`conteudo_bruto`.

    Instalado como *event hook* de resposta do cliente httpx, vale para qualquer requisição
    feita pelo coletor (JSON, CSV, ZIP...), inclusive novas tentativas e respostas de erro.
    Grava em transação própria, já confirmada, para que a resposta fique registrada mesmo
    quando a coleta falha e a sessão do coletor é desfeita.
    """

    def __init__(self, engine: Engine, coleta_id: int | None, fonte: str | None):
        self.engine = engine
        self.coleta_id = coleta_id
        self.fonte = fonte

    def __call__(self, response: httpx.Response) -> None:
        original = response.read()
        sha_original = hashlib.sha256(original).hexdigest()
        redator: Redator | None = response.request.extensions.get(_EXT_REDATOR)
        gravado, redacao = (original, None)
        if redator is not None and response.is_success:
            gravado, redacao = redator(original)
        sha_gravado = hashlib.sha256(gravado).hexdigest()
        with self.engine.begin() as conn:
            conn.execute(
                pg_insert(ConteudoBruto)
                .values(
                    sha256=sha_gravado,
                    tamanho=len(gravado),
                    corpo_gzip=gzip.compress(gravado, mtime=0),
                )
                .on_conflict_do_nothing(index_elements=[ConteudoBruto.sha256])
            )
            resposta_id = conn.execute(
                insert(RespostaBruta)
                .values(
                    coleta_id=self.coleta_id,
                    fonte=self.fonte,
                    metodo=response.request.method,
                    url=str(response.request.url),
                    status_http=response.status_code,
                    content_type=response.headers.get("content-type"),
                    recebida_em=datetime.now(UTC),
                    sha256_original=sha_original,
                    tamanho_original=len(original),
                    sha256_gravado=sha_gravado,
                    redacao=redacao,
                )
                .returning(RespostaBruta.id)
            ).scalar_one()
        # permite ao coletor ligar o dado gravado à resposta de origem
        response.request.extensions[_EXT_RESPOSTA_ID] = resposta_id


@contextmanager
def gravar_respostas(
    client: httpx.Client, session: Session, coleta: Coleta | None, fonte: str | None = None
) -> Iterator[GravadorRespostas]:
    """Enquanto ativo, toda resposta recebida pelo `client` é gravada para auditoria."""
    gravador = GravadorRespostas(
        session.get_bind(), coleta.id if coleta else None, fonte or (coleta and coleta.fonte)
    )
    client.event_hooks["response"].append(gravador)
    try:
        yield gravador
    finally:
        client.event_hooks["response"].remove(gravador)


def resposta_id(response: httpx.Response) -> int | None:
    """Id em `resposta_bruta` da resposta (nulo se não havia gravação ativa)."""
    return response.request.extensions.get(_EXT_RESPOSTA_ID)


def get_json(
    client: httpx.Client,
    url: str,
    params: dict | None = None,
    *,
    decimal=False,
    redator: Redator | None = None,
    com_origem=False,
):
    """GET com novas tentativas para falhas de rede, 429 e 5xx.

    Com `decimal=True`, números com casas decimais viram `Decimal` (valores monetários).
    `redator` remove dados pessoais do que é gravado em `resposta_bruta` (o SHA-256 do
    original continua registrado). Com `com_origem=True`, devolve `(dados, resposta_id)`.
    """

    @retry(
        retry=retry_if_exception(_erro_transitorio),
        stop=stop_after_attempt(get_settings().http_tentativas),
        wait=wait_exponential(multiplier=2, max=30),
        reraise=True,
    )
    def _get():
        extensions = {_EXT_REDATOR: redator} if redator else None
        resp = client.get(url, params=params, extensions=extensions)
        resp.raise_for_status()
        if decimal:
            dados = json.loads(resp.content, parse_float=Decimal)
        else:
            dados = resp.json()
        return (dados, resposta_id(resp)) if com_origem else dados

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
    try:
        with gravar_respostas(client, session, coleta):
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
    coleta.finalizada_em = datetime.now(UTC)
    session.add(coleta)
    session.commit()
    return coleta
