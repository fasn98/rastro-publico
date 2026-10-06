"""Consulta das respostas brutas recebidas das fontes (trilha de auditoria)."""

import gzip
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rastro.db import get_session
from rastro.models import ConteudoBruto, RespostaBruta

router = APIRouter(prefix="/api", tags=["auditoria"])
SessionDep = Annotated[Session, Depends(get_session)]


class RespostaBrutaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    coleta_id: int | None
    fonte: str | None
    metodo: str
    url: str
    status_http: int
    content_type: str | None
    recebida_em: datetime
    sha256_original: str
    tamanho_original: int
    sha256_gravado: str
    redacao: str | None


class PaginaRespostas(BaseModel):
    total: int
    itens: list[RespostaBrutaOut]


@router.get("/coletas/{coleta_id}/respostas", response_model=PaginaRespostas)
def respostas_da_coleta(
    coleta_id: int,
    session: SessionDep,
    limite: Annotated[int, Query(ge=1, le=500)] = 100,
    deslocamento: Annotated[int, Query(ge=0)] = 0,
):
    filtro = RespostaBruta.coleta_id == coleta_id
    total = session.scalar(select(func.count()).select_from(RespostaBruta).where(filtro))
    itens = session.scalars(
        select(RespostaBruta)
        .where(filtro)
        .order_by(RespostaBruta.id)
        .limit(limite)
        .offset(deslocamento)
    ).all()
    return PaginaRespostas(total=total or 0, itens=itens)


def _resposta(session: Session, resposta_id: int) -> RespostaBruta:
    resposta = session.get(RespostaBruta, resposta_id)
    if resposta is None:
        raise HTTPException(404, "Resposta não encontrada")
    return resposta


@router.get("/respostas/{resposta_id}", response_model=RespostaBrutaOut)
def obter_resposta(resposta_id: int, session: SessionDep):
    return _resposta(session, resposta_id)


@router.get("/respostas/{resposta_id}/corpo")
def corpo_da_resposta(resposta_id: int, session: SessionDep):
    """Corpo gravado, byte a byte. Confira com `sha256sum`: deve dar `X-SHA256-Gravado`."""
    resposta = _resposta(session, resposta_id)
    conteudo = session.get(ConteudoBruto, resposta.sha256_gravado)
    return Response(
        gzip.decompress(conteudo.corpo_gzip),
        media_type=resposta.content_type or "application/octet-stream",
        headers={
            "X-SHA256-Original": resposta.sha256_original,
            "X-SHA256-Gravado": resposta.sha256_gravado,
            "X-Fonte-URL": resposta.url,
        },
    )
