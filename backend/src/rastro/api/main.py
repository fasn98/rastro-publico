import csv
import io
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rastro import indicadores as ind
from rastro import ranking as rk
from rastro.api.auditoria import router as auditoria
from rastro.db import get_session
from rastro.models import (
    Coleta,
    ContaDemonstrativo,
    DemonstrativoSiconfi,
    EnteSiconfi,
    Municipio,
    NotaRanking,
)

app = FastAPI(title="Rastro Público", version="0.1.0")
app.include_router(auditoria)
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
    periodo_final: bool


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


class Autonomia(Referencia):
    receita_tributaria: Decimal | None
    cota_icms: Decimal | None
    cota_ipva: Decimal | None
    cota_itr: Decimal | None
    despesa_administracao: Decimal | None
    despesa_legislativa: Decimal | None
    receita_local: Decimal | None
    custo_estrutura: Decimal | None
    razao: Decimal | None


class Liquidez(Referencia):
    caixa_liquido_nao_vinculado: Decimal | None
    caixa_liquido_vinculado: Decimal | None
    rcl: Decimal | None
    percentual: Decimal | None
    percentual_com_vinculados: Decimal | None


class Investimento(Referencia):
    liquidado: Decimal | None
    empenhado: Decimal | None
    restos_a_pagar_nao_processados: Decimal | None
    receita_realizada: Decimal | None
    percentual: Decimal | None


class BlocoTransparencia(BaseModel):
    disponiveis: int
    esperados: int


class Transparencia(BaseModel):
    exercicio: int
    periodicidade_rgf: str
    blocos: dict[str, BlocoTransparencia]
    indice: Decimal
    provisorio: bool


class IndicadoresAno(BaseModel):
    cod_ibge: int
    exercicio: int
    pessoal: list[Pessoal]
    divida: Divida | None
    execucao: Execucao | None
    autonomia: Autonomia | None
    liquidez: Liquidez | None
    investimento: Investimento | None
    transparencia: Transparencia | None


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


# --- Ranking Fiscal -----------------------------------------------------------------------


class ItemRanking(BaseModel):
    cod_ibge: int
    nome: str
    populacao: int | None
    faixa: str | None
    nota: Decimal | None
    indicadores_faltantes: int
    posicao_geral: int | None
    posicao_faixa: int | None
    notas: dict[str, float | None]


class Ranking(BaseModel):
    versao: str
    hash_metodologia: str
    calculado_em: datetime
    exercicios: str
    itens: list[ItemRanking]


class DetalheRanking(BaseModel):
    cod_ibge: int
    versao: str
    hash_metodologia: str
    calculado_em: datetime
    exercicios: str
    faixa: str | None
    nota: Decimal | None
    indicadores_faltantes: int
    posicao_geral: int | None
    posicao_faixa: int | None
    total_com_nota: int
    total_faixa: int
    componentes: dict


def _versao_atual(session: Session, uf: str, versao: str | None) -> str:
    if versao:
        return versao
    atual = session.scalar(
        select(NotaRanking.versao)
        .where(NotaRanking.uf == uf)
        .order_by(NotaRanking.calculado_em.desc())
        .limit(1)
    )
    if not atual:
        raise HTTPException(404, f"Ranking de {uf} ainda não calculado (rode `rastro ranking`)")
    return atual


def _consultar_ranking(session, uf, faixa, busca, versao):
    uf = uf.upper()
    versao = _versao_atual(session, uf, versao)
    q = (
        select(NotaRanking, EnteSiconfi.nome)
        .join(EnteSiconfi, EnteSiconfi.cod_ibge == NotaRanking.cod_ibge)
        .where(NotaRanking.uf == uf, NotaRanking.versao == versao)
    )
    if faixa:
        q = q.where(NotaRanking.faixa == faixa)
    if busca:
        q = q.where(func.unaccent(EnteSiconfi.nome).ilike(func.unaccent(f"%{busca}%")))
    q = q.order_by(NotaRanking.posicao_geral.asc().nulls_last(), EnteSiconfi.nome)
    return session.execute(q).all()


def _item(n: NotaRanking, nome: str) -> dict:
    return {
        "cod_ibge": n.cod_ibge,
        "nome": nome,
        "populacao": n.populacao,
        "faixa": n.faixa,
        "nota": n.nota,
        "indicadores_faltantes": n.indicadores_faltantes,
        "posicao_geral": n.posicao_geral,
        "posicao_faixa": n.posicao_faixa,
        "notas": {k: v["nota"] for k, v in n.componentes.items()},
    }


@app.get("/api/ranking", response_model=Ranking)
def obter_ranking(
    session: SessionDep,
    uf: str = "SP",
    faixa: str | None = None,
    busca: str | None = None,
    versao: str | None = None,
):
    linhas = _consultar_ranking(session, uf, faixa, busca, versao)
    if not linhas:
        raise HTTPException(404, "Nenhum município encontrado")
    primeira = linhas[0][0]
    return {
        "versao": primeira.versao,
        "hash_metodologia": primeira.hash_metodologia,
        "calculado_em": primeira.calculado_em,
        "exercicios": primeira.exercicios,
        "itens": [_item(n, nome) for n, nome in linhas],
    }


COLUNAS_CSV = ["autonomia", "pessoal", "liquidez", "investimento", "transparencia"]


@app.get("/api/ranking.csv")
def exportar_ranking(
    session: SessionDep,
    uf: str = "SP",
    faixa: str | None = None,
    busca: str | None = None,
    versao: str | None = None,
):
    linhas = _consultar_ranking(session, uf, faixa, busca, versao)
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";")
    w.writerow(
        ["posicao_geral", "posicao_faixa", "cod_ibge", "municipio", "populacao", "faixa", "nota",
         "indicadores_faltantes", *[f"nota_{c}" for c in COLUNAS_CSV],
         "versao_metodologia", "hash_metodologia", "exercicios"]
    )  # fmt: skip
    for n, nome in linhas:
        notas = {k: v["nota"] for k, v in n.componentes.items()}
        w.writerow(
            [n.posicao_geral, n.posicao_faixa, n.cod_ibge, nome, n.populacao, n.faixa, n.nota,
             n.indicadores_faltantes, *[notas.get(c) for c in COLUNAS_CSV],
             n.versao, n.hash_metodologia, n.exercicios]
        )  # fmt: skip
    # BOM: o Excel abre o CSV em UTF-8 sem estragar os acentos
    return Response(
        "\ufeff" + saida.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="ranking-fiscal-{uf.lower()}.csv"'},
    )


@app.get("/api/ranking/{cod_ibge}", response_model=DetalheRanking)
def obter_nota(cod_ibge: int, session: SessionDep, versao: str | None = None):
    ente = session.get(EnteSiconfi, cod_ibge)
    if not ente or not ente.uf:
        raise HTTPException(404, "Ente não encontrado")
    versao = _versao_atual(session, ente.uf, versao)
    n = session.scalars(
        select(NotaRanking).where(NotaRanking.cod_ibge == cod_ibge, NotaRanking.versao == versao)
    ).first()
    if not n:
        raise HTTPException(404, "Município sem nota nesta versão")
    base = select(func.count()).where(
        NotaRanking.uf == n.uf, NotaRanking.versao == versao, NotaRanking.nota.is_not(None)
    )
    return {
        **{c: getattr(n, c) for c in DetalheRanking.model_fields if hasattr(n, c)},
        "total_com_nota": session.scalar(base),
        "total_faixa": session.scalar(base.where(NotaRanking.faixa == n.faixa)),
    }


@app.get("/api/metodologia")
def obter_metodologia():
    """Regras do arquivo de metodologia em vigor (pesos, normalização, faixas)."""
    met = rk.carregar_metodologia()
    return {"hash": met.hash, "exercicios": met.exercicios, **met.regras}
