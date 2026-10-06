"""RREO e RGF do SICONFI (API de Dados Abertos do Tesouro Nacional).

Fluxo por ente e exercício:

1. Lê o extrato de entregas para saber quais relatórios o ente entregou, em qual versão
   (completa ou simplificada), periodicidade e data do último status.
2. Pula os relatórios cuja data de status não mudou desde a última coleta.
3. Baixa os que são novos ou foram retificados e substitui o demonstrativo inteiro.

Documentação: https://apidatalake.tesouro.gov.br/docs/siconfi/
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from rastro.coletores.base import ColetaParcial
from rastro.coletores.siconfi import paginas
from rastro.config import get_settings
from rastro.models import ContaDemonstrativo, DemonstrativoSiconfi, EnteSiconfi

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


def entregas(client: httpx.Client, cod_ibge: int, exercicio: int) -> list[Entrega]:
    """RREO/RGF entregues pelo ente no exercício, um item por relatório e período.

    O RGF aparece uma vez por instituição (Prefeitura, Câmara...); fica a data de
    status mais recente, para que a retificação de qualquer poder dispare nova coleta.
    """
    mais_recente: dict[tuple[str, str, int], datetime | None] = {}
    params = {"id_ente": cod_ibge, "an_referencia": exercicio}
    for item in paginas(client, URL_EXTRATO, params):
        demonstrativo = DEMONSTRATIVO_POR_ENTREGAVEL.get(item["entregavel"])
        if not demonstrativo or item.get("exercicio", exercicio) != exercicio:
            continue
        chave = (demonstrativo, item["periodicidade"], item["periodo"])
        data = _data(item.get("data_status"))
        atual = mais_recente.get(chave)
        if chave not in mais_recente or (data and (atual is None or data > atual)):
            mais_recente[chave] = data
    return [Entrega(d, pc, p, data) for (d, pc, p), data in sorted(mais_recente.items())]


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
    intervalo = get_settings().siconfi_intervalo
    if e.demonstrativo.startswith("RREO"):
        params = {
            "an_exercicio": exercicio,
            "nr_periodo": e.periodo,
            "co_tipo_demonstrativo": e.demonstrativo,
            "id_ente": cod_ibge,
        }
        time.sleep(intervalo)
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
        time.sleep(intervalo)
        linhas = list(paginas(client, URL_RGF, params, decimal=True))
        if linhas:
            por_poder[poder] = linhas
    return por_poder


def _instituicao(linhas: list[dict]) -> str | None:
    nomes = sorted({i["instituicao"] for i in linhas if i.get("instituicao")})
    return "; ".join(nomes)[:200] or None


def gravar(session: Session, cod_ibge: int, exercicio: int, e: Entrega, por_poder: dict) -> int:
    """Substitui o relatório (todos os poderes) pelas linhas baixadas."""
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
    for poder, linhas in por_poder.items():
        cab = DemonstrativoSiconfi(
            cod_ibge=cod_ibge,
            exercicio=exercicio,
            demonstrativo=e.demonstrativo,
            periodicidade=e.periodicidade,
            periodo=e.periodo,
            poder=poder,
            instituicao=_instituicao(linhas),
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
    for e in entregas(client, ente.cod_ibge, exercicio):
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
