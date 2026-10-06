"""RREO e RGF do SICONFI (API de Dados Abertos do Tesouro Nacional).

Fluxo por ente e exercício:

1. Lê o extrato de entregas para saber quais relatórios o ente entregou, em qual versão
   (completa ou simplificada), periodicidade e data do último status.
2. Pula os relatórios cuja data de status não mudou desde a última coleta.
3. Baixa os que são novos ou foram retificados e substitui o demonstrativo inteiro.

Documentação: https://apidatalake.tesouro.gov.br/docs/siconfi/
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from rastro.coletores.base import ColetaParcial
from rastro.coletores.siconfi import paginas
from rastro.models import (
    ContaDemonstrativo,
    DemonstrativoSiconfi,
    EnteSiconfi,
    EntregaSiconfi,
    ExtratoColetado,
)

log = logging.getLogger(__name__)

URL_BASE = "https://apidatalake.tesouro.gov.br/ords/cdwhprd/siconfi/tt"
URL_EXTRATO = f"{URL_BASE}/extrato_entregas"
URL_RREO = f"{URL_BASE}/rreo"
URL_RGF = f"{URL_BASE}/rgf"

# Nome do item no extrato de entregas -> valor de co_tipo_demonstrativo nas consultas
DEMONSTRATIVO_POR_ENTREGAVEL = {
    "Relatório Resumido de Execução Orçamentária": "RREO",
    "Relatório Resumido de Execução Orçamentária Simplificado": "RREO Simplificado",
    "Relatório de Gestão Fiscal": "RGF",
    "Relatório de Gestão Fiscal Simplificado": "RGF Simplificado",
}

# Poderes que publicam RGF. Municípios só têm Executivo e Legislativo; no Legislativo
# entram a Câmara e, onde existe, o Tribunal de Contas do Município (ex.: São Paulo).
PODERES_POR_ESFERA = {
    "M": ("E", "L"),
    "E": ("E", "L", "J", "M", "D"),
    "D": ("E", "L", "J", "M", "D"),
    "U": ("E", "L", "J", "M", "D"),
}


@dataclass(frozen=True)
class Entrega:
    demonstrativo: str
    periodicidade: str
    periodo: int
    data_status: datetime | None


def _data(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor) if valor else None


def ler_extrato(client: httpx.Client, cod_ibge: int, exercicio: int) -> list[dict]:
    """Todas as entregas do ente no exercício (RREO, RGF, DCA, MSC...)."""
    params = {"id_ente": cod_ibge, "an_referencia": exercicio}
    return [
        i
        for i in paginas(client, URL_EXTRATO, params)
        if i.get("exercicio", exercicio) == exercicio
    ]


def gravar_extrato(session: Session, cod_ibge: int, exercicio: int, itens: list[dict]) -> None:
    """Guarda o extrato como foi lido (base do indicador de transparência)."""
    session.execute(
        delete(EntregaSiconfi).where(
            EntregaSiconfi.cod_ibge == cod_ibge, EntregaSiconfi.exercicio == exercicio
        )
    )
    session.add_all(
        EntregaSiconfi(
            cod_ibge=cod_ibge,
            exercicio=exercicio,
            entregavel=i["entregavel"],
            periodicidade=i.get("periodicidade"),
            periodo=i.get("periodo"),
            instituicao=i.get("instituicao"),
            status_relatorio=i.get("status_relatorio"),
            tipo_relatorio=i.get("tipo_relatorio"),
            forma_envio=i.get("forma_envio"),
            data_status=_data(i.get("data_status")),
            resposta_id=i.get("_resposta_id"),
        )
        for i in itens
    )
    session.merge(
        ExtratoColetado(
            cod_ibge=cod_ibge, exercicio=exercicio, itens=len(itens), lido_em=datetime.now(UTC)
        )
    )
    session.commit()


def entregas_de(itens: list[dict]) -> list[Entrega]:
    """RREO/RGF do extrato, um item por relatório e período.

    O RGF aparece uma vez por instituição (Prefeitura, Câmara...); fica a data de
    status mais recente, para que a retificação de qualquer poder dispare nova coleta.
    """
    mais_recente: dict[tuple[str, str, int], datetime | None] = {}
    for item in itens:
        demonstrativo = DEMONSTRATIVO_POR_ENTREGAVEL.get(item["entregavel"])
        if not demonstrativo:
            continue
        chave = (demonstrativo, item["periodicidade"], item["periodo"])
        data = _data(item.get("data_status"))
        atual = mais_recente.get(chave)
        if chave not in mais_recente or (data and (atual is None or data > atual)):
            mais_recente[chave] = data
    return [Entrega(d, pc, p, data) for (d, pc, p), data in sorted(mais_recente.items())]


def entregas(client: httpx.Client, cod_ibge: int, exercicio: int) -> list[Entrega]:
    return entregas_de(ler_extrato(client, cod_ibge, exercicio))


def _ja_coletado(session: Session, cod_ibge: int, exercicio: int, e: Entrega) -> bool:
    datas = session.scalars(
        select(DemonstrativoSiconfi.data_status).where(
            DemonstrativoSiconfi.cod_ibge == cod_ibge,
            DemonstrativoSiconfi.exercicio == exercicio,
            DemonstrativoSiconfi.demonstrativo == e.demonstrativo,
            DemonstrativoSiconfi.periodicidade == e.periodicidade,
            DemonstrativoSiconfi.periodo == e.periodo,
        )
    ).all()
    return bool(datas) and e.data_status is not None and all(d == e.data_status for d in datas)


def baixar(
    client: httpx.Client, cod_ibge: int, exercicio: int, esfera: str, e: Entrega
) -> dict[str | None, list[dict]]:
    """Linhas do relatório agrupadas por poder (chave None no RREO)."""
    if e.demonstrativo.startswith("RREO"):
        params = {
            "an_exercicio": exercicio,
            "nr_periodo": e.periodo,
            "co_tipo_demonstrativo": e.demonstrativo,
            "id_ente": cod_ibge,
        }
        return {None: list(paginas(client, URL_RREO, params, decimal=True))}

    por_poder: dict[str | None, list[dict]] = {}
    for poder in PODERES_POR_ESFERA[esfera]:
        params = {
            "an_exercicio": exercicio,
            "in_periodicidade": e.periodicidade,
            "nr_periodo": e.periodo,
            "co_tipo_demonstrativo": e.demonstrativo,
            "co_poder": poder,
            "id_ente": cod_ibge,
        }
        linhas = list(paginas(client, URL_RGF, params, decimal=True))
        if linhas:
            por_poder[poder] = linhas
    return por_poder


def _por_instituicao(linhas: list[dict]) -> dict[str | None, list[dict]]:
    """Separa as linhas por instituição.

    Um mesmo poder pode ter mais de uma (ex.: Câmara e Tribunal de Contas do Município
    no Legislativo de São Paulo), e cada uma entrega seu próprio RGF.
    """
    grupos: dict[str | None, list[dict]] = {}
    for linha in linhas:
        grupos.setdefault(linha.get("instituicao"), []).append(linha)
    return grupos


def gravar(session: Session, cod_ibge: int, exercicio: int, e: Entrega, por_poder: dict) -> int:
    """Substitui o relatório (todos os poderes e instituições) pelas linhas baixadas."""
    session.execute(
        delete(DemonstrativoSiconfi).where(
            DemonstrativoSiconfi.cod_ibge == cod_ibge,
            DemonstrativoSiconfi.exercicio == exercicio,
            DemonstrativoSiconfi.demonstrativo == e.demonstrativo,
            DemonstrativoSiconfi.periodicidade == e.periodicidade,
            DemonstrativoSiconfi.periodo == e.periodo,
        )
    )
    total = 0
    for poder, linhas_poder in por_poder.items():
        for instituicao, linhas in _por_instituicao(linhas_poder).items():
            cab = DemonstrativoSiconfi(
                cod_ibge=cod_ibge,
                exercicio=exercicio,
                demonstrativo=e.demonstrativo,
                periodicidade=e.periodicidade,
                periodo=e.periodo,
                poder=poder,
                instituicao=instituicao,
                data_status=e.data_status,
                linhas=len(linhas),
            )
            session.add(cab)
            session.flush()
            session.execute(
                ContaDemonstrativo.__table__.insert(),
                [
                    {
                        "demonstrativo_id": cab.id,
                        "anexo": i["anexo"],
                        "rotulo": i["rotulo"],
                        "coluna": i["coluna"],
                        "cod_conta": i["cod_conta"],
                        "conta": i["conta"],
                        "valor": i.get("valor"),
                        "resposta_id": i.get("_resposta_id"),
                    }
                    for i in linhas
                ],
            )
            total += len(linhas)
    session.commit()
    return total


def coletar_ente(
    session: Session,
    client: httpx.Client,
    ente: EnteSiconfi,
    exercicio: int,
    forcar: bool = False,
) -> int:
    total = 0
    itens = ler_extrato(client, ente.cod_ibge, exercicio)
    gravar_extrato(session, ente.cod_ibge, exercicio, itens)
    for e in entregas_de(itens):
        if not forcar and _ja_coletado(session, ente.cod_ibge, exercicio, e):
            continue
        por_poder = baixar(client, ente.cod_ibge, exercicio, ente.esfera, e)
        if not por_poder:
            # consta no extrato mas a API ainda não tem as linhas; tenta de novo na próxima
            log.warning(
                "%s (%s) %s %s%s/%s: entregue, mas sem dados na API",
                ente.nome, ente.cod_ibge, e.demonstrativo, e.periodo, e.periodicidade,
                exercicio,
            )  # fmt: skip
            continue
        n = gravar(session, ente.cod_ibge, exercicio, e, por_poder)
        log.info(
            "%s (%s) %s %s%s/%s: %d linhas",
            ente.nome, ente.cod_ibge, e.demonstrativo, e.periodo, e.periodicidade,
            exercicio, n,
        )  # fmt: skip
        total += n
    return total


def coletor(entes: list[EnteSiconfi], exercicios: list[int], forcar: bool = False):
    """Monta um coletor para `executar` que percorre entes x exercícios.

    Falha em um ente não interrompe os demais; ao final, se houve falhas,
    a coleta fica registrada como parcial (ou falha, se nada foi gravado).
    """

    def _coletar(session: Session, client: httpx.Client) -> int:
        total = 0
        erros: list[str] = []
        for ente in entes:
            for exercicio in exercicios:
                try:
                    total += coletar_ente(session, client, ente, exercicio, forcar)
                except Exception as exc:
                    session.rollback()
                    log.exception("Falha em %s (%s) %s", ente.nome, ente.cod_ibge, exercicio)
                    erros.append(f"{ente.cod_ibge} {exercicio}: {type(exc).__name__}: {exc}")
        if erros:
            if total == 0 and len(erros) == len(entes) * len(exercicios):
                raise RuntimeError("\n".join(erros))
            raise ColetaParcial(total, erros)
        return total

    return _coletar


def selecionar_entes(
    session: Session,
    codigos: list[int] | None = None,
    ufs: list[str] | None = None,
    esferas: list[str] | None = None,
) -> list[EnteSiconfi]:
    q = select(EnteSiconfi).order_by(EnteSiconfi.cod_ibge)
    if codigos:
        q = q.where(EnteSiconfi.cod_ibge.in_(codigos))
    if ufs:
        q = q.where(EnteSiconfi.uf.in_([u.upper() for u in ufs]))
    if esferas:
        q = q.where(EnteSiconfi.esfera.in_([e.upper() for e in esferas]))
    return list(session.scalars(q))
