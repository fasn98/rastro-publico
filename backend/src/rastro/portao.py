"""Portão de qualidade por UF antes de publicar (ADR-0020).

Uma UF só entra no site se passar nas três conferências, nesta ordem:

1. **Completude:** todo ente da UF no SICONFI (municípios, estado ou DF) tem o extrato de
   entregas lido em cada exercício do ranking, e a última tentativa de coleta de cada um
   terminou sem falha. Assim, cada município aparece com dado ou como "não reportado",
   nunca como "ainda não coletado".
2. **Arquivo bruto:** numa amostra das respostas guardadas da UF, os bytes conferem com o
   SHA-256 registrado.
3. **Fonte:** em 3 entes sorteados (sorteio registrado, repetível pela data e pela UF), o
   último RREO guardado é baixado de novo da API do SICONFI e comparado, célula por célula,
   com o que está no banco. Se a fonte retificou o relatório depois da coleta, não é
   divergência: a próxima coleta relê.

Uma UF reprovada fica fora do site (ou com a versão publicada antes), sem bloquear as
demais. O resultado vai para o manifesto.
"""

import logging
import random
import zlib
from datetime import date
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from rastro import mapeamento as mp
from rastro.coletores import siconfi_demonstrativos as sd
from rastro.coletores.arquivo import ler_payload
from rastro.coletores.siconfi import UF_POR_CODIGO
from rastro.indicadores import _prioridade
from rastro.models import (
    ContaDemonstrativo,
    DemonstrativoResposta,
    DemonstrativoSiconfi,
    EnteSiconfi,
    ExtratoColetado,
    ItemLote,
    PayloadBruto,
    RespostaBruta,
)

log = logging.getLogger(__name__)

UFS = tuple(sorted(UF_POR_CODIGO.values()))
ESFERAS = ("M", "E", "D")
AMOSTRA_HASHES = 20
SORTEADOS = 3
EXEMPLOS = 10  # quantos casos citar em cada motivo de reprovação


def _entes(session: Session, uf: str) -> list[EnteSiconfi]:
    return list(
        session.scalars(
            select(EnteSiconfi)
            .where(EnteSiconfi.uf == uf, EnteSiconfi.esfera.in_(ESFERAS))
            .order_by(EnteSiconfi.cod_ibge)
        )
    )


def completude(session: Session, entes: list[EnteSiconfi], exercicios: list[int]) -> dict:
    cods = [e.cod_ibge for e in entes]
    lidos = set(
        session.execute(
            select(ExtratoColetado.cod_ibge, ExtratoColetado.exercicio).where(
                ExtratoColetado.cod_ibge.in_(cods), ExtratoColetado.exercicio.in_(exercicios)
            )
        ).all()
    )
    # última tentativa de cada (ente, exercício), em qualquer lote
    ultima: dict[tuple[int, int], str] = {}
    for cod, ano, status in session.execute(
        select(ItemLote.cod_ibge, ItemLote.exercicio, ItemLote.status)
        .where(
            ItemLote.cod_ibge.in_(cods),
            ItemLote.exercicio.in_(exercicios),
            ItemLote.tentativas > 0,
        )
        .order_by(ItemLote.atualizado_em.asc().nulls_first())
    ):
        ultima[(cod, ano)] = status
    esperados = [(c, a) for c in cods for a in exercicios]
    sem_extrato = [k for k in esperados if k not in lidos]
    com_falha = [k for k in esperados if k in lidos and ultima.get(k, "sucesso") != "sucesso"]
    return {
        "entes": len(cods),
        "esperados": len(esperados),
        "sem_extrato": len(sem_extrato),
        "com_falha": len(com_falha),
        "exemplos": [f"{c}/{a}" for c, a in (sem_extrato + com_falha)[:EXEMPLOS]],
    }


def conferir_hashes(
    session: Session, entes: list[EnteSiconfi], rng: random.Random, n: int = AMOSTRA_HASHES
) -> dict:
    ids = sorted(
        session.scalars(
            select(DemonstrativoResposta.resposta_id)
            .join(
                DemonstrativoSiconfi,
                DemonstrativoSiconfi.id == DemonstrativoResposta.demonstrativo_id,
            )
            .where(DemonstrativoSiconfi.cod_ibge.in_([e.cod_ibge for e in entes]))
            .distinct()
        )
    )
    amostra = sorted(rng.sample(ids, min(n, len(ids))))
    divergentes = []
    for rid in amostra:
        r = session.get(RespostaBruta, rid)
        p = session.get(PayloadBruto, r.sha256) if r else None
        try:
            if p is None:
                raise ValueError("resposta sem conteúdo guardado")
            ler_payload(p)
        # SHA-256 diferente (ValueError) ou bytes que nem descomprimem (gzip truncado)
        except (ValueError, EOFError, OSError, zlib.error):
            divergentes.append(rid)
    return {"conferidas": len(amostra), "divergentes": divergentes}


def _celulas(linhas) -> set[tuple]:
    return {
        (
            i["anexo"],
            i["rotulo"],
            i["coluna"],
            i["cod_conta"],
            i["conta"],
            None if i.get("valor") is None else Decimal(str(i["valor"])),
        )
        for i in linhas
    }


def conferir_fonte(
    session: Session,
    client: httpx.Client,
    entes: list[EnteSiconfi],
    exercicios: list[int],
    rng: random.Random,
    n: int = SORTEADOS,
) -> list[dict]:
    """Baixa de novo o último RREO guardado de `n` entes sorteados e compara com o banco."""
    por_cod = {e.cod_ibge: e for e in entes}
    # lidos antes de qualquer consulta à fonte: depois do commit, o objeto seria recarregado
    nomes = {e.cod_ibge: (e.nome, e.esfera) for e in entes}
    ultimo: dict[int, DemonstrativoSiconfi] = {}
    for d in session.scalars(
        select(DemonstrativoSiconfi)
        .where(
            DemonstrativoSiconfi.cod_ibge.in_(list(por_cod)),
            DemonstrativoSiconfi.exercicio.in_(exercicios),
            DemonstrativoSiconfi.demonstrativo.startswith("RREO"),
        )
        .order_by(DemonstrativoSiconfi.exercicio, DemonstrativoSiconfi.periodo)
    ):
        atual = ultimo.get(d.cod_ibge)
        # a Prefeitura (ou o Governo) antes de outra instituição com o mesmo código (D1)
        if (
            atual is None
            or (d.exercicio, d.periodo) > (atual.exercicio, atual.periodo)
            or (
                (d.exercicio, d.periodo) == (atual.exercicio, atual.periodo)
                and _prioridade(d.instituicao) < _prioridade(atual.instituicao)
            )
        ):
            ultimo[d.cod_ibge] = d
    sorteados = sorted(rng.sample(sorted(ultimo), min(n, len(ultimo))))
    mapeamento = mp.padrao()
    resultados = []
    for cod in sorteados:
        d = ultimo[cod]
        guardado = (d.id, d.exercicio, d.demonstrativo, d.periodicidade, d.periodo, d.instituicao)
        celulas_banco = _celulas(
            {
                "anexo": c.anexo,
                "rotulo": c.rotulo,
                "coluna": c.coluna,
                "cod_conta": c.cod_conta,
                "conta": c.conta,
                "valor": c.valor,
            }
            for c in session.scalars(
                select(ContaDemonstrativo).where(ContaDemonstrativo.demonstrativo_id == d.id)
            )
        )
        data_guardada = d.data_status
        # nada fica pendente no banco durante as consultas à fonte (transação ociosa)
        session.commit()
        _, ano, demonstrativo, periodicidade, periodo, instituicao = guardado
        r = {
            "cod_ibge": cod,
            "nome": nomes[cod][0],
            "relatorio": f"{demonstrativo} {periodo}{periodicidade}/{ano}",
        }
        entregas = sd.entregas_de(sd.ler_extrato(client, cod, ano))
        entrega = next(
            (
                e
                for e in entregas
                if (e.demonstrativo, e.periodicidade, e.periodo)
                == (demonstrativo, periodicidade, periodo)
            ),
            None,
        )
        if entrega is None:
            resultados.append({**r, "ok": False, "situacao": "não consta mais no extrato da fonte"})
            continue
        if entrega.data_status != data_guardada:
            resultados.append({**r, "ok": True, "situacao": "retificado na fonte depois da coleta"})
            continue
        linhas = sd.baixar(client, cod, ano, nomes[cod][1], entrega).get(None, [])
        da_instituicao = [i for i in linhas if i.get("instituicao") == instituicao]
        celulas_fonte = _celulas(
            sd._sem_duplicatas([i for i in da_instituicao if mapeamento.aceita(i)], cod)
        )
        diferencas = len(celulas_fonte ^ celulas_banco)
        resultados.append(
            {
                **r,
                "ok": diferencas == 0,
                "situacao": "confere"
                if diferencas == 0
                else f"{diferencas} célula(s) diferente(s) da fonte",
                "celulas": len(celulas_banco),
            }
        )
    return resultados


def avaliar_uf(
    session: Session,
    client: httpx.Client,
    uf: str,
    exercicios: list[int],
    hoje: date,
) -> dict:
    uf = uf.upper()
    entes = _entes(session, uf)
    rng = random.Random(f"{uf}:{hoje.isoformat()}")
    resultado: dict = {"uf": uf, "aprovada": False, "motivos": []}
    if not entes:
        resultado["motivos"].append("nenhum ente da UF no cadastro do SICONFI")
        return resultado

    comp = completude(session, entes, exercicios)
    resultado["completude"] = comp
    if comp["sem_extrato"] or comp["com_falha"]:
        resultado["motivos"].append(
            f"coleta incompleta: {comp['sem_extrato']} ente-exercício(s) sem extrato lido e "
            f"{comp['com_falha']} com falha na última tentativa, de {comp['esperados']}"
        )
        return resultado

    hashes = conferir_hashes(session, entes, rng)
    resultado["arquivo_bruto"] = hashes
    if hashes["divergentes"]:
        resultado["motivos"].append(
            f"arquivo bruto: {len(hashes['divergentes'])} de {hashes['conferidas']} respostas "
            "com SHA-256 que não confere"
        )
        return resultado

    try:
        fonte = conferir_fonte(session, client, entes, exercicios, rng)
    except Exception as exc:  # fonte fora do ar: a UF não é aprovada nesta coleta
        session.rollback()
        resultado["motivos"].append(
            f"conferência com a fonte não pôde ser feita ({type(exc).__name__}: {exc})"
        )
        return resultado
    resultado["sorteados"] = fonte
    if not fonte:
        resultado["motivos"].append("nenhum RREO guardado nos exercícios do ranking")
    divergentes = [f for f in fonte if not f["ok"]]
    for f in divergentes:
        resultado["motivos"].append(
            f"{f['nome']} ({f['cod_ibge']}), {f['relatorio']}: {f['situacao']}"
        )
    resultado["aprovada"] = not resultado["motivos"]
    return resultado


def avaliar(
    session: Session,
    client: httpx.Client,
    exercicios: list[int],
    hoje: date,
    ufs: list[str] | None = None,
) -> dict[str, dict]:
    resultados = {}
    for uf in ufs or UFS:
        resultados[uf] = avaliar_uf(session, client, uf, exercicios, hoje)
        r = resultados[uf]
        log.info(
            "Portão %s: %s%s",
            uf,
            "aprovada" if r["aprovada"] else "reprovada",
            "" if r["aprovada"] else f" ({'; '.join(r['motivos'])})",
        )
    return resultados
