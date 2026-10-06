from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rastro import indicadores as ind
from rastro.db import get_session
from rastro.models import (
    Coleta,
    ContaDemonstrativo,
    DemonstrativoSiconfi,
    EnteSiconfi,
    Municipio,
)

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


class DemonstrativoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cod_ibge: int
    exercicio: int
    demonstrativo: str
    periodicidade: str
    periodo: int
    poder: str | None
    instituicao: str | None
    data_status: datetime | None
    linhas: int
    coletado_em: datetime


class ContaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    anexo: str
    rotulo: str
    coluna: str
    cod_conta: str
    conta: str
    valor: Decimal | None


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


@app.get("/api/entes/{cod_ibge}/demonstrativos", response_model=list[DemonstrativoOut])
def listar_demonstrativos(
    cod_ibge: int,
    session: SessionDep,
    exercicio: int | None = None,
    demonstrativo: str | None = None,
):
    q = select(DemonstrativoSiconfi).where(DemonstrativoSiconfi.cod_ibge == cod_ibge)
    if exercicio:
        q = q.where(DemonstrativoSiconfi.exercicio == exercicio)
    if demonstrativo:
        q = q.where(DemonstrativoSiconfi.demonstrativo == demonstrativo)
    q = q.order_by(
        DemonstrativoSiconfi.exercicio.desc(),
        DemonstrativoSiconfi.demonstrativo,
        DemonstrativoSiconfi.periodo,
        DemonstrativoSiconfi.poder,
    )
    return session.scalars(q).all()


@app.get("/api/demonstrativos/{demonstrativo_id}/contas", response_model=list[ContaOut])
def listar_contas(
    demonstrativo_id: int,
    session: SessionDep,
    anexo: str | None = None,
    cod_conta: str | None = None,
):
    if not session.get(DemonstrativoSiconfi, demonstrativo_id):
        raise HTTPException(404, "Demonstrativo não encontrado")
    q = select(ContaDemonstrativo).where(ContaDemonstrativo.demonstrativo_id == demonstrativo_id)
    if anexo:
        q = q.where(ContaDemonstrativo.anexo == anexo)
    if cod_conta:
        q = q.where(ContaDemonstrativo.cod_conta == cod_conta)
    return session.scalars(q.order_by(ContaDemonstrativo.id)).all()


class Referencia(BaseModel):
    demonstrativo_id: int
    demonstrativo: str
    periodicidade: str
    periodo: int


class Pessoal(Referencia):
    poder: str | None
    nome_poder: str | None
    instituicao: str | None
    despesa_total_pessoal: Decimal | None
    rcl_ajustada: Decimal | None
    percentual: Decimal | None
    limite_alerta: Decimal | None
    limite_prudencial: Decimal | None
    limite_maximo: Decimal | None
    situacao: str | None


class Divida(Referencia):
    divida_consolidada_liquida: Decimal | None
    rcl_ajustada: Decimal | None
    percentual: Decimal | None
    limite_alerta: Decimal | None
    limite_maximo: Decimal | None
    situacao: str | None


class Execucao(Referencia):
    receita_prevista: Decimal | None
    receita_realizada: Decimal | None
    despesa_dotacao: Decimal | None
    despesa_empenhada: Decimal | None
    despesa_liquidada: Decimal | None
    despesa_paga: Decimal | None
    resultado: Decimal | None
    superavit_financeiro_utilizado: Decimal | None


class IndicadoresAno(BaseModel):
    cod_ibge: int
    exercicio: int
    pessoal: list[Pessoal]
    divida: Divida | None
    execucao: Execucao | None


class Indicadores(IndicadoresAno):
    exercicios_disponiveis: list[int]


@app.get("/api/entes/{cod_ibge}/indicadores", response_model=Indicadores)
def obter_indicadores(cod_ibge: int, session: SessionDep, exercicio: int | None = None):
    """Indicadores fiscais do último período disponível do exercício (padrão: o mais recente)."""
    disponiveis = ind.exercicios_disponiveis(session, cod_ibge)
    if exercicio is None:
        if not disponiveis:
            raise HTTPException(404, "Nenhum RREO/RGF coletado para este ente")
        exercicio = disponiveis[0]
    return {**ind.indicadores(session, cod_ibge, exercicio), "exercicios_disponiveis": disponiveis}


@app.get("/api/entes/{cod_ibge}/indicadores/serie", response_model=list[IndicadoresAno])
def obter_serie(cod_ibge: int, session: SessionDep):
    """Indicadores de todos os exercícios coletados, do mais antigo ao mais recente."""
    return ind.serie(session, cod_ibge)
