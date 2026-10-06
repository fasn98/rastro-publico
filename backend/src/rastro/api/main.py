from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rastro.db import get_session
from rastro.models import Coleta, EnteSiconfi, Municipio

app = FastAPI(title="Rastro Público", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

SessionDep = Annotated[Session, Depends(get_session)]


class MunicipioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    cod_ibge: int
    nome: str
    uf: str
    regiao: str
    regiao_imediata: str | None
    regiao_intermediaria: str | None


class EnteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    cod_ibge: int
    nome: str
    esfera: str
    uf: str | None
    capital: bool
    populacao: int | None
    cnpj: str | None
    exercicio: int


class MunicipioDetalhe(MunicipioOut):
    ente_siconfi: EnteOut | None


class Pagina[T](BaseModel):
    total: int
    itens: list[T]


class ColetaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    fonte: str
    status: str
    registros: int | None
    erro: str | None
    iniciada_em: datetime
    finalizada_em: datetime | None


@app.get("/api/saude")
def saude():
    return {"status": "ok"}


@app.get("/api/municipios", response_model=Pagina[MunicipioOut])
def listar_municipios(
    session: SessionDep,
    uf: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    nome: Annotated[str | None, Query(min_length=2)] = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    q = select(Municipio)
    if uf:
        q = q.where(Municipio.uf == uf.upper())
    if nome:
        q = q.where(func.unaccent(Municipio.nome).ilike(func.unaccent(f"%{nome}%")))
    total = session.scalar(select(func.count()).select_from(q.subquery()))
    itens = session.scalars(q.order_by(Municipio.nome).limit(limite).offset(offset)).all()
    return {"total": total, "itens": itens}


@app.get("/api/municipios/{cod_ibge}", response_model=MunicipioDetalhe)
def obter_municipio(cod_ibge: int, session: SessionDep):
    m = session.get(Municipio, cod_ibge)
    if not m:
        raise HTTPException(404, "Município não encontrado")
    ente = session.get(EnteSiconfi, cod_ibge)
    return {**MunicipioOut.model_validate(m).model_dump(), "ente_siconfi": ente}


@app.get("/api/coletas", response_model=list[ColetaOut])
def ultimas_coletas(session: SessionDep, limite: Annotated[int, Query(ge=1, le=100)] = 20):
    return session.scalars(select(Coleta).order_by(Coleta.id.desc()).limit(limite)).all()
