"""API do módulo de políticos. Só fatos com fonte; ordenação neutra (alfabética/cronológica)."""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import extract, func, or_, select
from sqlalchemy.orm import Session

from rastro.db import get_session
from rastro.models import Coleta, Municipio, RespostaBruta
from rastro.politicos import transparencia
from rastro.politicos.modelos import (
    CARGOS_ESTADUAIS,
    CARGOS_MUNICIPAIS,
    DEPUTADO_ESTADUAL,
    DEPUTADO_FEDERAL,
    GOVERNADOR,
    PREFEITO,
    SENADOR,
    VEREADOR,
    PolComissao,
    PolEmenda,
    PolPolitico,
    PolPresenca,
    PolProposicao,
    PolVotacao,
)

router = APIRouter(prefix="/api", tags=["políticos"])
SessionDep = Annotated[Session, Depends(get_session)]

PENDENTE_TSE = (
    "Eleitos do TSE ainda não carregados: o Portal de Dados Abertos do TSE não está "
    "acessível no ambiente de coleta. Ver README, seção Políticos."
)


class Fonte(BaseModel):
    """Resposta oficial de onde o dado saiu: URL, data da coleta e cópia arquivada."""

    url: str
    recebido_em: datetime
    resposta_id: int


class PoliticoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fonte: str
    id_fonte: str
    nome: str
    partido: str | None
    cargo: str
    uf: str
    cod_ibge: int | None
    situacao: str | None
    em_exercicio: bool | None
    legislatura: int | None
    mandato_inicio: date | None
    mandato_fim: date | None
    eleicao_ano: int | None
    url_fonte: str
    url_pagina: str | None
    resposta_id: int | None
    atualizado_em: datetime


class Pagina[T](BaseModel):
    total: int
    itens: list[T]


class Contagem(BaseModel):
    ano: int
    quantidade: int
    fontes: list[Fonte]


class ContagemVotos(Contagem):
    por_voto: dict[str, int]  # voto como registrado na fonte -> quantidade


class ComissaoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sigla: str
    nome: str
    casa: str | None
    participacao: str | None
    data_inicio: date | None
    data_fim: date | None
    url_fonte: str
    resposta_id: int | None


class PoliticoDetalhe(PoliticoOut):
    fonte_registro: Fonte | None
    proposicoes: list[Contagem]
    votacoes: list[ContagemVotos]
    presencas: list[Contagem]
    comissoes: list[ComissaoOut]
    # descrição de cada código de voto, quando a fonte a fornece (ex.: Senado "AP")
    descricao_votos: dict[str, str]


class ProposicaoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_fonte: str
    sigla_tipo: str | None
    numero: str | None
    ano: int
    ementa: str | None
    data_apresentacao: date | None
    autoria: str | None
    url_fonte: str
    url_pagina: str | None
    resposta_id: int | None


class VotacaoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_votacao: str
    data: date
    voto: str
    voto_descricao: str | None
    orgao: str | None
    materia: str | None
    descricao: str | None
    url_fonte: str
    resposta_id: int | None


class PresencaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_evento: str
    data_hora_inicio: datetime
    url_fonte: str
    resposta_id: int | None


class EmendaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    codigo_emenda: str
    ano: int
    tipo_emenda: str | None
    transferencia_especial: bool
    nome_autor: str | None
    numero_emenda: str | None
    localidade_gasto: str | None
    cod_ibge_destino: int | None
    funcao: str | None
    subfuncao: str | None
    valor_empenhado: Decimal | None
    valor_liquidado: Decimal | None
    valor_pago: Decimal | None
    url_fonte: str
    resposta_id: int | None


class TotalEmendas(BaseModel):
    ano: int
    transferencia_especial: bool
    quantidade: int
    valor_empenhado: Decimal
    valor_liquidado: Decimal
    valor_pago: Decimal


class Emendas(BaseModel):
    coletadas: bool  # houve coleta de emendas com sucesso
    aviso: str | None
    totais: list[TotalEmendas]
    itens: list[EmendaOut]


class GrupoRepresentantes(BaseModel):
    cargo: str
    politicos: list[PoliticoOut]
    pendente: str | None


class MunicipioRef(BaseModel):
    cod_ibge: int
    nome: str
    uf: str


class Representantes(BaseModel):
    municipio: MunicipioRef
    grupos: list[GrupoRepresentantes]


def _ordem_nome():
    return (func.unaccent(PolPolitico.nome), PolPolitico.id)


def _politico(session: Session, politico_id: int) -> PolPolitico:
    p = session.get(PolPolitico, politico_id)
    if p is None:
        raise HTTPException(404, "Político não encontrado")
    return p


def _municipio(session: Session, cod_ibge: int) -> Municipio:
    m = session.get(Municipio, cod_ibge)
    if m is None:
        raise HTTPException(404, "Município não encontrado")
    return m


def _fontes(session: Session, ids: set[int]) -> list[Fonte]:
    if not ids:
        return []
    rows = session.execute(
        select(RespostaBruta.id, RespostaBruta.url, RespostaBruta.recebido_em)
        .where(RespostaBruta.id.in_(ids))
        .order_by(RespostaBruta.id)
    )
    return [Fonte(resposta_id=i, url=u, recebido_em=r) for i, u, r in rows]


def _contagens(session: Session, modelo, coluna_ano, politico_id: int) -> list[Contagem]:
    ano = coluna_ano.label("ano")
    rows = session.execute(
        select(ano, func.count(), func.array_agg(func.distinct(modelo.resposta_id)))
        .where(modelo.politico_id == politico_id)
        .group_by(ano)
        .order_by(ano)
    )
    return [
        Contagem(ano=int(a), quantidade=n, fontes=_fontes(session, {r for r in rids if r}))
        for a, n, rids in rows
    ]


@router.get("/politicos", response_model=Pagina[PoliticoOut])
def listar_politicos(
    session: SessionDep,
    uf: str | None = None,
    cargo: str | None = None,
    municipio: Annotated[int | None, Query(description="código IBGE")] = None,
    nome: str | None = None,
    em_exercicio: bool | None = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 200,
    deslocamento: Annotated[int, Query(ge=0)] = 0,
):
    """Ordem alfabética por nome. `municipio` traz os cargos do município e os do estado."""
    q = select(PolPolitico)
    if uf:
        q = q.where(PolPolitico.uf == uf.upper())
    if cargo:
        q = q.where(PolPolitico.cargo == cargo)
    if municipio is not None:
        m = _municipio(session, municipio)
        q = q.where(
            or_(
                PolPolitico.cod_ibge == municipio,
                (PolPolitico.uf == m.uf) & PolPolitico.cargo.in_(CARGOS_ESTADUAIS),
            )
        )
    if nome:
        q = q.where(func.unaccent(PolPolitico.nome).ilike(func.unaccent(f"%{nome}%")))
    if em_exercicio is not None:
        q = q.where(PolPolitico.em_exercicio.is_(em_exercicio))
    total = session.scalar(select(func.count()).select_from(q.subquery()))
    itens = session.scalars(q.order_by(*_ordem_nome()).limit(limite).offset(deslocamento)).all()
    return Pagina(total=total or 0, itens=itens)


@router.get("/politicos/{politico_id}", response_model=PoliticoDetalhe)
def detalhe_politico(politico_id: int, session: SessionDep):
    p = _politico(session, politico_id)
    votos = defaultdict(dict)
    ano_voto = extract("year", PolVotacao.data)
    for a, voto, n in session.execute(
        select(ano_voto, PolVotacao.voto, func.count())
        .where(PolVotacao.politico_id == p.id)
        .group_by(ano_voto, PolVotacao.voto)
    ):
        votos[int(a)][voto] = n
    votacoes = [
        ContagemVotos(**c.model_dump(), por_voto=dict(sorted(votos[c.ano].items())))
        for c in _contagens(session, PolVotacao, ano_voto, p.id)
    ]
    descricoes = dict(
        session.execute(
            select(PolVotacao.voto, PolVotacao.voto_descricao)
            .where(PolVotacao.politico_id == p.id, PolVotacao.voto_descricao.is_not(None))
            .distinct()
        ).all()
    )
    registro = _fontes(session, {p.resposta_id} if p.resposta_id else set())
    return PoliticoDetalhe(
        **PoliticoOut.model_validate(p).model_dump(),
        fonte_registro=registro[0] if registro else None,
        descricao_votos=descricoes,
        proposicoes=_contagens(session, PolProposicao, PolProposicao.ano, p.id),
        votacoes=votacoes,
        presencas=_contagens(
            session, PolPresenca, extract("year", PolPresenca.data_hora_inicio), p.id
        ),
        comissoes=session.scalars(
            select(PolComissao)
            .where(PolComissao.politico_id == p.id)
            .order_by(PolComissao.data_inicio.desc().nulls_last(), PolComissao.sigla)
        ).all(),
    )


def _pagina(session: Session, q, ordem, limite: int, deslocamento: int):
    total = session.scalar(select(func.count()).select_from(q.subquery()))
    itens = session.scalars(q.order_by(*ordem).limit(limite).offset(deslocamento)).all()
    return Pagina(total=total or 0, itens=itens)


Limite = Annotated[int, Query(ge=1, le=500)]
Deslocamento = Annotated[int, Query(ge=0)]


@router.get("/politicos/{politico_id}/proposicoes", response_model=Pagina[ProposicaoOut])
def proposicoes(
    politico_id: int,
    session: SessionDep,
    ano: int | None = None,
    limite: Limite = 100,
    deslocamento: Deslocamento = 0,
):
    _politico(session, politico_id)
    q = select(PolProposicao).where(PolProposicao.politico_id == politico_id)
    if ano:
        q = q.where(PolProposicao.ano == ano)
    ordem = (PolProposicao.data_apresentacao.desc().nulls_last(), PolProposicao.id_fonte)
    return _pagina(session, q, ordem, limite, deslocamento)


@router.get("/politicos/{politico_id}/votacoes", response_model=Pagina[VotacaoOut])
def votacoes(
    politico_id: int,
    session: SessionDep,
    ano: int | None = None,
    limite: Limite = 100,
    deslocamento: Deslocamento = 0,
):
    _politico(session, politico_id)
    q = select(PolVotacao).where(PolVotacao.politico_id == politico_id)
    if ano:
        q = q.where(extract("year", PolVotacao.data) == ano)
    return _pagina(
        session, q, (PolVotacao.data.desc(), PolVotacao.id_votacao), limite, deslocamento
    )


@router.get("/politicos/{politico_id}/presencas", response_model=Pagina[PresencaOut])
def presencas(
    politico_id: int,
    session: SessionDep,
    ano: int | None = None,
    limite: Limite = 100,
    deslocamento: Deslocamento = 0,
):
    _politico(session, politico_id)
    q = select(PolPresenca).where(PolPresenca.politico_id == politico_id)
    if ano:
        q = q.where(extract("year", PolPresenca.data_hora_inicio) == ano)
    ordem = (PolPresenca.data_hora_inicio.desc(), PolPresenca.id_evento)
    return _pagina(session, q, ordem, limite, deslocamento)


def _emendas(session: Session, filtro, ano: int | None) -> Emendas:
    q = select(PolEmenda).where(filtro)
    if ano:
        q = q.where(PolEmenda.ano == ano)
    itens = session.scalars(q.order_by(PolEmenda.ano.desc(), PolEmenda.codigo_emenda)).all()
    totais: dict[tuple[int, bool], TotalEmendas] = {}
    for e in itens:
        t = totais.setdefault(
            (e.ano, e.transferencia_especial),
            TotalEmendas(
                ano=e.ano,
                transferencia_especial=e.transferencia_especial,
                quantidade=0,
                valor_empenhado=Decimal(0),
                valor_liquidado=Decimal(0),
                valor_pago=Decimal(0),
            ),
        )
        t.quantidade += 1
        t.valor_empenhado += e.valor_empenhado or 0
        t.valor_liquidado += e.valor_liquidado or 0
        t.valor_pago += e.valor_pago or 0
    coletadas = bool(
        session.scalar(
            select(func.count())
            .select_from(Coleta)
            .where(Coleta.fonte == "pol-emendas", Coleta.status.in_(["sucesso", "parcial"]))
        )
    )
    aviso = None
    if not coletadas:
        aviso = (
            "Emendas ainda não coletadas: o coletor do Portal da Transparência está "
            "desligado até haver chave de API configurada."
        )
        if transparencia.chave():
            aviso = "Emendas ainda não coletadas: rode `rastro politicos --fontes emendas`."
    return Emendas(
        coletadas=coletadas,
        aviso=aviso,
        totais=sorted(totais.values(), key=lambda t: (-t.ano, t.transferencia_especial)),
        itens=itens,
    )


@router.get("/politicos/{politico_id}/emendas", response_model=Emendas)
def emendas_do_politico(politico_id: int, session: SessionDep, ano: int | None = None):
    _politico(session, politico_id)
    return _emendas(session, PolEmenda.politico_id == politico_id, ano)


@router.get("/municipios/{cod_ibge}/emendas", response_model=Emendas)
def emendas_do_municipio(cod_ibge: int, session: SessionDep, ano: int | None = None):
    _municipio(session, cod_ibge)
    return _emendas(session, PolEmenda.cod_ibge_destino == cod_ibge, ano)


@router.get("/municipios/{cod_ibge}/representantes", response_model=Representantes)
def representantes(cod_ibge: int, session: SessionDep):
    """Quem ocupa hoje cada cargo que representa o município, em ordem alfabética."""
    m = _municipio(session, cod_ibge)
    grupos = []
    for cargo in (PREFEITO, VEREADOR, GOVERNADOR, SENADOR, DEPUTADO_FEDERAL, DEPUTADO_ESTADUAL):
        q = select(PolPolitico).where(PolPolitico.cargo == cargo, PolPolitico.uf == m.uf)
        if cargo in CARGOS_MUNICIPAIS:
            q = q.where(PolPolitico.cod_ibge == cod_ibge)
        if cargo in (SENADOR, DEPUTADO_FEDERAL):
            q = q.where(PolPolitico.em_exercicio.is_(True))
        politicos = session.scalars(q.order_by(*_ordem_nome())).all()
        pendente = (
            PENDENTE_TSE if not politicos and cargo not in (SENADOR, DEPUTADO_FEDERAL) else None
        )
        grupos.append(GrupoRepresentantes(cargo=cargo, politicos=politicos, pendente=pendente))
    return Representantes(
        municipio=MunicipioRef(cod_ibge=m.cod_ibge, nome=m.nome, uf=m.uf), grupos=grupos
    )
