"""Coleta em lote, retomável, do RREO/RGF de muitos entes em vários exercícios.

Uso (comando único, pensado para rodar agendado):

    python -m rastro.coletores.siconfi_lote --uf SP --anos 2022-2025

O lote e cada item (ente x exercício) ficam gravados no banco. Se o processo for
interrompido, rodar o mesmo comando de novo retoma de onde parou: itens concluídos
são pulados e os que falharam são tentados de novo (até --max-tentativas). Dentro de
um item, relatórios já gravados e não retificados também não são baixados de novo.

As requisições respeitam RASTRO_REQ_POR_SEGUNDO (padrão: 1 por segundo).
"""

import argparse
import logging
import signal
import sys
import time
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from rastro.coletores import siconfi
from rastro.coletores.arquivo import coleta_atual
from rastro.coletores.base import executar, novo_cliente
from rastro.coletores.siconfi_demonstrativos import coletar_ente, selecionar_entes
from rastro.db import get_sessionmaker
from rastro.models import Coleta, EnteSiconfi, ItemLote, LoteColeta

log = logging.getLogger(__name__)


def interpretar_anos(texto: str) -> list[int]:
    """'2022-2025' -> [2022, 2023, 2024, 2025]; '2022,2024' -> [2022, 2024]."""
    anos: set[int] = set()
    for parte in texto.split(","):
        if "-" in parte:
            ini, fim = (int(x) for x in parte.split("-"))
            anos.update(range(min(ini, fim), max(ini, fim) + 1))
        else:
            anos.add(int(parte))
    return sorted(anos)


def chave_lote(ufs: list[str], anos: list[int], entes: list[int], esferas: list[str]) -> str:
    partes = [
        "uf=" + ",".join(sorted(u.upper() for u in ufs)),
        "esfera=" + ",".join(sorted(e.upper() for e in esferas)),
        "anos=" + ",".join(map(str, anos)),
        "entes=" + ",".join(map(str, sorted(entes))),
    ]
    return ";".join(partes)


def abrir_lote(
    session: Session, entes: list[EnteSiconfi], anos: list[int], chave: str, novo: bool = False
) -> tuple[LoteColeta, bool]:
    """Retoma o último lote aberto com a mesma chave, ou cria um novo. Devolve (lote, retomado)."""
    if not novo:
        aberto = session.scalars(
            select(LoteColeta)
            .where(LoteColeta.chave == chave, LoteColeta.finalizado_em.is_(None))
            .order_by(LoteColeta.id.desc())
        ).first()
        if aberto:
            return aberto, True
    lote = LoteColeta(chave=chave)
    session.add(lote)
    session.flush()
    session.add_all(
        ItemLote(lote_id=lote.id, cod_ibge=e.cod_ibge, exercicio=a, status="pendente", tentativas=0)
        for e in entes
        for a in anos
    )
    session.commit()
    return lote, False


def _duracao(segundos: float) -> str:
    segundos = int(segundos)
    h, resto = divmod(segundos, 3600)
    return f"{h}h{resto // 60:02d}" if h else f"{resto // 60}min{resto % 60:02d}s"


def executar_lote(
    session: Session,
    client: httpx.Client,
    lote: LoteColeta,
    forcar: bool = False,
    max_tentativas: int = 3,
) -> dict:
    entes = {
        e.cod_ibge: e
        for e in session.scalars(
            select(EnteSiconfi).where(
                EnteSiconfi.cod_ibge.in_(
                    select(ItemLote.cod_ibge).where(ItemLote.lote_id == lote.id)
                )
            )
        )
    }
    pendentes = session.scalars(
        select(ItemLote)
        .where(
            ItemLote.lote_id == lote.id,
            ItemLote.status != "sucesso",
            ItemLote.tentativas < max_tentativas,
        )
        .order_by(ItemLote.cod_ibge, ItemLote.exercicio)
    ).all()
    total_itens = session.query(ItemLote).filter(ItemLote.lote_id == lote.id).count()
    feitos_antes = total_itens - len(pendentes)
    log.info(
        "Lote %s: %d itens, %d já concluídos ou esgotados, %d a processar",
        lote.id, total_itens, feitos_antes, len(pendentes),
    )  # fmt: skip

    inicio = time.monotonic()
    linhas = 0
    for n, item in enumerate(pendentes, start=1):
        ente = entes[item.cod_ibge]
        # gravado antes de coletar: um rollback por falha não pode desfazer a contagem
        item.tentativas += 1
        session.commit()
        try:
            item.linhas = coletar_ente(session, client, ente, item.exercicio, forcar)
            item.status = "sucesso"
            item.erro = None
            linhas += item.linhas
        except Exception as exc:
            session.rollback()
            item.status = "falha"
            item.erro = f"{type(exc).__name__}: {exc}"
            log.warning("Falha em %s (%s) %s: %s", ente.nome, ente.cod_ibge, item.exercicio, exc)
        item.atualizado_em = datetime.now(UTC)
        session.commit()

        decorrido = time.monotonic() - inicio
        restante = decorrido / n * (len(pendentes) - n)
        log.info(
            "[%d/%d] %s %s: %s · %s decorridos · faltam ~%s",
            feitos_antes + n, total_itens, ente.nome, item.exercicio,
            f"{item.linhas} linhas" if item.status == "sucesso" else "FALHA",
            _duracao(decorrido), _duracao(restante),
        )  # fmt: skip

    contagem = dict.fromkeys(("sucesso", "falha", "pendente"), 0)
    for status in session.scalars(select(ItemLote.status).where(ItemLote.lote_id == lote.id)):
        contagem[status] = contagem.get(status, 0) + 1
    if contagem["sucesso"] == total_itens:
        lote.finalizado_em = datetime.now(UTC)
        session.commit()
    return {"lote": lote.id, "linhas": linhas, "itens": total_itens, **contagem}


def _garantir_entes(session: Session) -> None:
    if session.query(EnteSiconfi).count() == 0:
        log.info("Tabela de entes vazia: coletando entes do SICONFI primeiro")
        with novo_cliente() as client:
            executar(session, "siconfi-entes", siconfi.coletar, client)


def _interromper(_sinal, _frame):
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m rastro.coletores.siconfi_lote",
        description="Coleta RREO/RGF em lote, retomável.",
    )
    p.add_argument("--anos", required=True, help="ex.: 2022-2025 ou 2023,2025")
    p.add_argument("--uf", nargs="+", default=[], help="ex.: SP")
    p.add_argument("--esfera", nargs="+", default=["M"], help="padrão: M (municípios)")
    p.add_argument("--ente", type=int, nargs="+", default=[], help="códigos IBGE (amostra)")
    p.add_argument("--novo", action="store_true", help="ignora lote aberto e começa outro")
    p.add_argument("--forcar", action="store_true", help="baixa de novo mesmo sem retificação")
    p.add_argument("--max-tentativas", type=int, default=3)
    args = p.parse_args(argv)
    if not args.uf and not args.ente:
        p.error("informe --uf ou --ente")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    anos = interpretar_anos(args.anos)

    # SIGTERM (ex.: fim do tempo de um agendador) vira KeyboardInterrupt para sair limpo
    signal.signal(signal.SIGTERM, _interromper)

    with get_sessionmaker()() as session:
        _garantir_entes(session)
        entes = selecionar_entes(session, args.ente or None, args.uf or None, args.esfera)
        if not entes:
            print("Nenhum ente encontrado para os filtros informados.", file=sys.stderr)
            return 1
        chave = chave_lote(args.uf, anos, args.ente, args.esfera)
        lote, retomado = abrir_lote(session, entes, anos, chave, args.novo)
        print(
            f"{'Retomando' if retomado else 'Iniciando'} lote {lote.id}: "
            f"{len(entes)} entes x {len(anos)} exercícios ({chave})"
        )
        coleta = Coleta(fonte="siconfi-lote", status="executando")
        session.add(coleta)
        session.commit()
        coleta_atual.set(coleta.id)  # liga cada resposta bruta a esta coleta
        try:
            with novo_cliente() as client:
                resumo = executar_lote(session, client, lote, args.forcar, args.max_tentativas)
        except KeyboardInterrupt:
            session.rollback()
            coleta.status = "interrompida"
            coleta.finalizada_em = datetime.now(UTC)
            session.commit()
            print("Interrompido. Rode o mesmo comando para retomar.", file=sys.stderr)
            return 130
        coleta.registros = resumo["linhas"]
        coleta.status = "sucesso" if resumo["sucesso"] == resumo["itens"] else "parcial"
        coleta.erro = None if coleta.status == "sucesso" else f"{resumo}"
        coleta.finalizada_em = datetime.now(UTC)
        session.commit()
    print(
        f"Lote {resumo['lote']}: {resumo['sucesso']}/{resumo['itens']} itens concluídos, "
        f"{resumo['falha']} com falha, {resumo['linhas']} linhas gravadas nesta execução"
    )
    return 0 if resumo["sucesso"] == resumo["itens"] else 1


if __name__ == "__main__":
    sys.exit(main())
