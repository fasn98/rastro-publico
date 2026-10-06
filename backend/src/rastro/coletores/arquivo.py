"""Arquivo de respostas brutas: todo número do portal é auditável até a resposta original.

Toda resposta HTTP recebida por um cliente criado com `novo_cliente()` é guardada antes
de qualquer processamento, em transação própria (o registro sobrevive mesmo se a coleta
falhar ou for desfeita depois):

- `payload_bruto`: os bytes exatamente como chegaram, comprimidos com gzip e indexados
  pelo SHA-256 dos bytes ORIGINAIS (não dos comprimidos). Conteúdo idêntico é guardado
  uma única vez.
- `resposta_bruta`: cada chamada (URL completa com parâmetros, método, status HTTP,
  content-type, data, duração, SHA-256 e a coleta em que ocorreu).

O id da resposta fica em `response.extensions["resposta_id"]`; os coletores o gravam junto
de cada valor que extraem (ex.: `conta_demonstrativo.resposta_id`).

Redação (LGPD): quando a fonte devolve dados pessoais (CPF, data de nascimento, título de
eleitor, e-mail...), o coletor passa um `Redator` na requisição (`com_redacao(redator)`
como `extensions` do httpx). O original NÃO é guardado: grava-se só a versão redigida,
com o SHA-256 do original (`sha256_original`), o da versão gravada (`sha256`) e a lista
de campos removidos. A conferência, nesses casos, é baixar de novo a URL pública da
fonte e comparar com `sha256_original`. Se o redator falhar, nada é gravado e a
requisição falha (nunca se grava o original por engano).
"""

import gzip
import hashlib
import logging
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
from sqlalchemy import Engine, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from rastro.models import PayloadBruto, RespostaBruta

log = logging.getLogger(__name__)

# coleta em andamento; definida por `executar` e pelo lote para ligar resposta -> coleta
coleta_atual: ContextVar[int | None] = ContextVar("coleta_atual", default=None)


def sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


@dataclass
class Redacao:
    """Resultado de um redator: o que gravar e o que foi removido."""

    conteudo: bytes
    campos_removidos: list[str] = field(default_factory=list)
    descricao: str = ""


Redator = Callable[[bytes], Redacao]
_EXT_REDATOR = "rastro_redator"


def com_redacao(redator: Redator | None) -> dict | None:
    """`extensions` do httpx para que a resposta seja arquivada já redigida."""
    return {_EXT_REDATOR: redator} if redator else None


class ArquivoBruto:
    """Gancho de resposta do httpx que arquiva cada resposta recebida."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def __call__(self, response: httpx.Response) -> None:
        original = response.read()
        redator: Redator | None = response.request.extensions.get(_EXT_REDATOR)
        redacao = None
        # respostas de erro (4xx/5xx) não trazem os dados da fonte; são gravadas como vieram
        if redator is not None and response.is_success:
            redacao = redator(original)  # se falhar, nada é gravado
        conteudo = redacao.conteudo if redacao else original
        digest = sha256(conteudo)
        try:
            duracao = int(response.elapsed.total_seconds() * 1000)
        except RuntimeError:  # elapsed só existe depois de a resposta ser fechada
            duracao = None
        with self.engine.begin() as conn:
            conn.execute(
                pg_insert(PayloadBruto)
                .values(
                    sha256=digest,
                    tamanho=len(conteudo),
                    compressao="gzip",
                    conteudo=gzip.compress(conteudo, mtime=0),
                )
                .on_conflict_do_nothing(index_elements=["sha256"])
            )
            resposta_id = conn.execute(
                insert(RespostaBruta)
                .values(
                    coleta_id=coleta_atual.get(),
                    metodo=response.request.method,
                    url=str(response.request.url),
                    status_http=response.status_code,
                    content_type=response.headers.get("content-type"),
                    recebido_em=datetime.now(UTC),
                    duracao_ms=duracao,
                    sha256=digest,
                    tamanho=len(conteudo),
                    sha256_original=sha256(original) if redacao else None,
                    tamanho_original=len(original) if redacao else None,
                    campos_removidos=redacao.campos_removidos if redacao else None,
                    redacao=redacao.descricao if redacao else None,
                )
                .returning(RespostaBruta.id)
            ).scalar_one()
        response.extensions["resposta_id"] = resposta_id


def resposta_id(response: httpx.Response) -> int | None:
    return response.extensions.get("resposta_id")


def ler_payload(p: PayloadBruto) -> bytes:
    """Bytes originais; levanta ValueError se o conteúdo não bater com o SHA-256."""
    conteudo = gzip.decompress(p.conteudo) if p.compressao == "gzip" else p.conteudo
    if sha256(conteudo) != p.sha256:
        raise ValueError(f"payload {p.sha256} corrompido: SHA-256 não confere")
    return conteudo
