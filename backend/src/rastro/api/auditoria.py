"""API de auditoria: o único pedaço do portal que consulta o banco em produção.

O site publicado é estático (gerado por `rastro exportar-site`). Ele chama só estes
endpoints, para baixar a resposta original de uma fonte e verificar o SHA-256 dela:

    GET /api/respostas/{id}                         metadados + verificação de integridade
    GET /api/respostas/{id}/bruto                   bytes originais
    GET /api/demonstrativos/{id}/respostas          respostas que formam um relatório
    GET /api/bruto/{sha256}                         bytes gravados, pelo SHA-256 deles

O endereço por hash não depende de ids do banco: o mesmo link vale em qualquer exportação
(é o que permite a exportação incremental). Os endpoints por id continuam valendo.

Em produção roda sozinha (`uvicorn rastro.api.auditoria:app`), com CORS limitado à origem
do site (RASTRO_CORS_ORIGENS). Respostas brutas nunca mudam (são endereçadas pelo
SHA-256), então vão com cache longo e ETag; o banco só acorda quando o cache não atende.
"""

from collections import OrderedDict
from datetime import datetime
from threading import Lock
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from rastro.coletores.arquivo import ler_payload
from rastro.config import get_settings
from rastro.db import get_session
from rastro.models import ContaDemonstrativo, DemonstrativoResposta, PayloadBruto, RespostaBruta

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]

# conteúdo endereçado por hash não muda: o navegador pode guardar por 1 ano
IMUTAVEL = "public, max-age=31536000, immutable"
# a lista de respostas de um demonstrativo muda se o relatório for retificado
CURTO = "public, max-age=3600"


class _CacheBytes:
    """Cache LRU em memória dos payloads já verificados (por SHA-256)."""

    def __init__(self, limite_bytes: int):
        self.limite = limite_bytes
        self.itens: OrderedDict[str, bytes] = OrderedDict()
        self.total = 0
        self.trava = Lock()

    def get(self, chave: str) -> bytes | None:
        with self.trava:
            if chave in self.itens:
                self.itens.move_to_end(chave)
                return self.itens[chave]
            return None

    def put(self, chave: str, valor: bytes) -> None:
        if len(valor) > self.limite:
            return
        with self.trava:
            if chave in self.itens:
                return
            self.itens[chave] = valor
            self.total += len(valor)
            while self.total > self.limite:
                _, velho = self.itens.popitem(last=False)
                self.total -= len(velho)

    def limpar(self) -> None:
        with self.trava:
            self.itens.clear()
            self.total = 0


cache_payloads = _CacheBytes(64 * 1024 * 1024)


class RespostaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    coleta_id: int | None
    metodo: str
    url: str
    status_http: int
    content_type: str | None
    recebido_em: datetime
    duracao_ms: int | None
    sha256: str  # do conteúdo gravado
    tamanho: int
    # preenchidos quando o conteúdo foi gravado sem dados pessoais (LGPD)
    sha256_original: str | None
    tamanho_original: int | None
    campos_removidos: list[str] | None
    redacao: str | None


class RespostaVerificada(RespostaOut):
    integra: bool  # SHA-256 recalculado agora sobre os bytes guardados confere?
    url_bruto: str


def _payload(session: Session, sha: str, usar_cache: bool = True) -> bytes:
    """Bytes originais verificados (levanta ValueError se o hash não conferir)."""
    if usar_cache:
        em_cache = cache_payloads.get(sha)
        if em_cache is not None:
            return em_cache
    conteudo = ler_payload(session.get(PayloadBruto, sha))
    cache_payloads.put(sha, conteudo)
    return conteudo


def _nao_modificado(request: Request, etag: str) -> bool:
    return request.headers.get("if-none-match") == etag


@router.get("/respostas/{resposta_id}", response_model=RespostaVerificada)
def obter_resposta(resposta_id: int, session: SessionDep, response: Response):
    """Metadados de uma chamada à fonte, com verificação de integridade do payload."""
    r = session.get(RespostaBruta, resposta_id)
    if not r:
        raise HTTPException(404, "Resposta não encontrada")
    try:
        # a verificação relê do banco e recalcula o hash, sem cache: é o que ela promete
        _payload(session, r.sha256, usar_cache=False)
        integra = True
    except ValueError:
        integra = False
    if integra:
        response.headers["Cache-Control"] = IMUTAVEL
    return {
        **RespostaOut.model_validate(r).model_dump(),
        "integra": integra,
        "url_bruto": f"/api/respostas/{r.id}/bruto",
    }


@router.get("/respostas/{resposta_id}/bruto")
def baixar_resposta(resposta_id: int, session: SessionDep, request: Request):
    """Os bytes gravados (confira com sha256sum).

    São os bytes exatamente como a fonte devolveu, exceto quando a resposta foi gravada
    com redação (LGPD): aí vêm sem os campos pessoais, e o cabeçalho
    `X-Rastro-SHA256-Original` traz o hash do original, para conferir baixando de novo a URL.
    """
    r = session.get(RespostaBruta, resposta_id)
    if not r:
        raise HTTPException(404, "Resposta não encontrada")
    etag = f'"{r.sha256}"'
    cabecalhos = {
        "ETag": etag,
        "Cache-Control": IMUTAVEL,
        "X-Rastro-SHA256": r.sha256,
        "X-Rastro-URL-Origem": r.url,
        "X-Rastro-Recebido-Em": r.recebido_em.isoformat(),
    }
    if r.sha256_original:
        cabecalhos["X-Rastro-SHA256-Original"] = r.sha256_original
        cabecalhos["X-Rastro-Campos-Removidos"] = ",".join(r.campos_removidos or [])
    if _nao_modificado(request, etag):
        return Response(status_code=304, headers=cabecalhos)
    try:
        conteudo = _payload(session, r.sha256)
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc
    return Response(
        conteudo, media_type=r.content_type or "application/octet-stream", headers=cabecalhos
    )


@router.get("/bruto/{sha}")
def bruto_por_hash(
    sha: Annotated[str, Path(pattern="^[0-9a-f]{64}$", description="SHA-256 do conteúdo gravado")],
    session: SessionDep,
    request: Request,
):
    """Os bytes gravados com este SHA-256 (confira com sha256sum).

    São os bytes exatamente como a fonte devolveu, exceto nas respostas gravadas com
    redação (LGPD): aí vêm sem os campos pessoais, `X-Rastro-SHA256` é o hash da versão
    gravada e `X-Rastro-SHA256-Original` o do original, para conferir baixando de novo a
    URL da fonte (`X-Rastro-URL-Origem`).
    """
    p = session.get(PayloadBruto, sha)
    if p is None:
        raise HTTPException(404, "Conteúdo não encontrado")
    # respostas que gravaram este conteúdo (a mesma resposta pode ter vindo mais de uma vez)
    respostas = session.scalars(
        select(RespostaBruta).where(RespostaBruta.sha256 == sha).order_by(RespostaBruta.id)
    ).all()
    etag = f'"{sha}"'
    cabecalhos = {"ETag": etag, "Cache-Control": IMUTAVEL, "X-Rastro-SHA256": sha}
    if respostas:
        primeira = respostas[0]
        cabecalhos["X-Rastro-URL-Origem"] = primeira.url
        cabecalhos["X-Rastro-Recebido-Em"] = primeira.recebido_em.isoformat()
    originais = sorted({r.sha256_original for r in respostas if r.sha256_original})
    if originais:
        cabecalhos["X-Rastro-SHA256-Original"] = ",".join(originais)
        campos = sorted({c for r in respostas for c in (r.campos_removidos or [])})
        cabecalhos["X-Rastro-Campos-Removidos"] = ",".join(campos)
    if _nao_modificado(request, etag):
        return Response(status_code=304, headers=cabecalhos)
    try:
        conteudo = _payload(session, sha)
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc
    tipo = respostas[0].content_type if respostas else None
    return Response(conteudo, media_type=tipo or "application/octet-stream", headers=cabecalhos)


@router.get("/demonstrativos/{demonstrativo_id}/respostas", response_model=list[RespostaOut])
def respostas_do_demonstrativo(demonstrativo_id: int, session: SessionDep, response: Response):
    """Respostas brutas de onde veio um demonstrativo (uma por página)."""
    ids = select(DemonstrativoResposta.resposta_id).where(
        DemonstrativoResposta.demonstrativo_id == demonstrativo_id
    )
    # dados anteriores à tabela demonstrativo_resposta: a origem está nas linhas
    ids_linhas = select(ContaDemonstrativo.resposta_id).where(
        ContaDemonstrativo.demonstrativo_id == demonstrativo_id
    )
    response.headers["Cache-Control"] = CURTO
    return session.scalars(
        select(RespostaBruta)
        .where(RespostaBruta.id.in_(ids) | RespostaBruta.id.in_(ids_linhas))
        .order_by(RespostaBruta.id)
    ).all()


def criar_app() -> FastAPI:
    """App só de auditoria, para produção."""
    app = FastAPI(title="Rastro Público — auditoria", version="1.0.0")
    app.include_router(router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().origens_cors,
        allow_methods=["GET"],
        allow_headers=["If-None-Match"],
        expose_headers=[
            "X-Rastro-SHA256",
            "X-Rastro-URL-Origem",
            "X-Rastro-Recebido-Em",
            "X-Rastro-SHA256-Original",
            "X-Rastro-Campos-Removidos",
            "ETag",
        ],
    )

    @app.get("/api/saude")
    def saude():
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def raiz():
        # verificação de saúde do provedor; não acessa o banco
        return {
            "servico": "rastro-publico auditoria",
            "site": "https://fasn98.github.io/rastro-publico/",
        }

    return app


app = criar_app()
