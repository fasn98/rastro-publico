"""Coleta em lote, retomável, do RREO/RGF de muitos entes em vários exercícios.

Uso (comando único, pensado para rodar agendado):

    python -m rastro.coletores.siconfi_lote --uf SP --anos 2022-2025

O lote e cada item (ente x exercício) ficam gravados no banco. Se o processo for
interrompido, rodar o mesmo comando de novo retoma de onde parou: itens concluídos
são pulados e os que falharam são tentados de novo (até --max-tentativas). Dentro de
um item, relatórios já gravados e não retificados também não são baixados de novo.

As requisições respeitam RASTRO_REQ_POR_SEGUNDO (padrão: 1 por segundo).

Coleta nacional (ADR-0020):

    python -m rastro.coletores.siconfi_lote --uf TODAS --esfera M E D --anos 2022-2026 \
        --prioridade 2023-2025 --limite-minutos 480 --rodizio

- ordem: primeiro os exercícios de --prioridade, UF por UF, das UFs com menos municípios
  para as com mais; depois os demais exercícios, do mais recente para o mais antigo;
- --limite-minutos: não começa item novo depois desse tempo. O que faltar fica para a
  próxima execução (o lote continua aberto), e o resto da coleta (ranking, site) roda;
- --rodizio: num lote novo, o exercício corrente e o anterior entram sempre; os mais
  antigos entram em rodízio de 4 semanas (um quarto dos entes por semana), ou se nunca
  foram lidos, ou se a última leitura tem mais de 35 dias.
"""

import argparse
import logging
import signal
import sys
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from rastro.coletores import siconfi
from rastro.coletores.arquivo import coleta_atual
from rastro.coletores.base import executar, novo_cliente
from rastro.coletores.siconfi_demonstrativos import coletar_ente, selecionar_entes
from rastro.db import get_sessionmaker
from rastro.models import Coleta, EnteSiconfi, ExtratoColetado, ItemLote, LoteColeta

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


TODAS = "TODAS"
SEMANAS_RODIZIO = 4
# leitura mais antiga que isso entra no lote novo mesmo fora da semana do rodízio
IDADE_MAXIMA = timedelta(days=35)
# no rodízio, não relê o que foi lido há menos disso (coleta diária na mesma semana)
IDADE_MINIMA = timedelta(days=6)


def rodizio(session: Session, agora: datetime) -> Callable[[EnteSiconfi, int], bool]:
    """Filtro dos itens de um lote novo (ADR-0020).

    O exercício corrente e o anterior entram sempre: é neles que chegam os relatórios novos
    e quase todas as retificações. Os mais antigos entram se nunca foram lidos, se a última
    leitura passou de 35 dias, ou na semana do rodízio do ente (código IBGE módulo 4), desde
    que a última leitura tenha mais de 6 dias. Uma retificação de exercício antigo leva até
    4 semanas para aparecer.
    """
    lidos = {
        (cod, ano): lido
        for cod, ano, lido in session.execute(
            select(ExtratoColetado.cod_ibge, ExtratoColetado.exercicio, ExtratoColetado.lido_em)
        )
    }
    semana = agora.isocalendar().week % SEMANAS_RODIZIO

    def incluir(ente: EnteSiconfi, ano: int) -> bool:
        if ano >= agora.year - 1:
            return True
        lido = lidos.get((ente.cod_ibge, ano))
        if lido is None or agora - lido > IDADE_MAXIMA:
            return True
        return ente.cod_ibge % SEMANAS_RODIZIO == semana and agora - lido > IDADE_MINIMA

    return incluir


def ordem_das_ufs(session: Session) -> dict[str | None, int]:
    """Posição de cada UF: da que tem menos municípios no SICONFI para a que tem mais
    (empate: ordem alfabética da sigla)."""
    contagem = Counter(
        session.scalars(select(EnteSiconfi.uf).where(EnteSiconfi.esfera == "M")).all()
    )
    return {uf: i for i, uf in enumerate(sorted(contagem, key=lambda u: (contagem[u], u or "")))}


def abrir_lote(
    session: Session,
    entes: list[EnteSiconfi],
    anos: list[int],
    chave: str,
    novo: bool = False,
    incluir: Callable[[EnteSiconfi, int], bool] | None = None,
) -> tuple[LoteColeta, bool]:
    """Retoma o último lote aberto com a mesma chave, ou cria um novo. Devolve (lote, retomado).

    `incluir` filtra os itens (ente, exercício) de um lote novo (ver `rodizio`).
    """
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
        if incluir is None or incluir(e, a)
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
    prioridade: list[int] | None = None,
    limite_segundos: float | None = None,
) -> dict:
    """Coleta os itens pendentes do lote, na ordem de `_ordem`.

    Com `limite_segundos`, não começa item novo depois desse tempo: o que faltar continua
    pendente e o lote fica aberto para a próxima execução. O lote é finalizado quando não
    resta nada a tentar (todos com sucesso, ou com as tentativas esgotadas); os esgotados
    voltam no próximo lote.
    """
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
        select(ItemLote).where(
            ItemLote.lote_id == lote.id,
            ItemLote.status != "sucesso",
            ItemLote.tentativas < max_tentativas,
        )
    ).all()
    posicao_uf = ordem_das_ufs(session)
    prioritarios = set(prioridade or [])

    def _ordem(item: ItemLote):
        ente = entes[item.cod_ibge]
        fora = item.exercicio not in prioritarios
        return (
            fora and bool(prioritarios),  # primeiro os exercícios prioritários
            posicao_uf.get(ente.uf, len(posicao_uf)),
            ente.uf or "",
            item.cod_ibge,
            -item.exercicio if fora and prioritarios else item.exercicio,
        )

    pendentes.sort(key=_ordem)
    total_itens = session.query(ItemLote).filter(ItemLote.lote_id == lote.id).count()
    feitos_antes = total_itens - len(pendentes)
    log.info(
        "Lote %s: %d itens, %d já concluídos ou esgotados, %d a processar",
        lote.id, total_itens, feitos_antes, len(pendentes),
    )  # fmt: skip

    inicio = time.monotonic()
    linhas = 0
    parado_por_tempo = False
    for n, item in enumerate(pendentes, start=1):
        if limite_segundos is not None and time.monotonic() - inicio >= limite_segundos:
            parado_por_tempo = True
            log.info(
                "Limite de tempo do lote (%s) atingido: %d itens ficam para a próxima execução",
                _duracao(limite_segundos), len(pendentes) - n + 1,
            )  # fmt: skip
            break
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
    a_tentar = 0
    for status, tentativas in session.execute(
        select(ItemLote.status, ItemLote.tentativas).where(ItemLote.lote_id == lote.id)
    ):
        contagem[status] = contagem.get(status, 0) + 1
        a_tentar += status != "sucesso" and tentativas < max_tentativas
    # nada mais a tentar: finaliza, mesmo com itens esgotados (voltam no próximo lote);
    # antes, um item esgotado deixava o lote aberto para sempre, e nenhuma execução
    # seguinte relia os extratos
    if a_tentar == 0:
        lote.finalizado_em = datetime.now(UTC)
        session.commit()
    return {
        "lote": lote.id,
        "linhas": linhas,
        "itens": total_itens,
        "a_tentar": a_tentar,
        "parado_por_tempo": parado_por_tempo,
        **contagem,
    }


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
    p.add_argument("--uf", nargs="+", default=[], help="ex.: SP; TODAS = todas as UFs")
    p.add_argument("--esfera", nargs="+", default=["M"], help="padrão: M (municípios)")
    p.add_argument("--ente", type=int, nargs="+", default=[], help="códigos IBGE (amostra)")
    p.add_argument("--novo", action="store_true", help="ignora lote aberto e começa outro")
    p.add_argument("--forcar", action="store_true", help="baixa de novo mesmo sem retificação")
    p.add_argument("--max-tentativas", type=int, default=3)
    p.add_argument("--prioridade", help="exercícios coletados primeiro, UF por UF (ex.: 2023-2025)")
    p.add_argument("--limite-minutos", type=float, help="não começa item novo depois desse tempo")
    p.add_argument(
        "--rodizio",
        action="store_true",
        help="lote novo: exercícios antigos em rodízio de 4 semanas (ver `rodizio`)",
    )
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
        ufs = [] if [u.upper() for u in args.uf] == [TODAS] else args.uf
        entes = selecionar_entes(session, args.ente or None, ufs or None, args.esfera)
        if not entes:
            print("Nenhum ente encontrado para os filtros informados.", file=sys.stderr)
            return 1
        chave = chave_lote(args.uf, anos, args.ente, args.esfera)
        incluir = rodizio(session, datetime.now(UTC)) if args.rodizio else None
        lote, retomado = abrir_lote(session, entes, anos, chave, args.novo, incluir)
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
                resumo = executar_lote(
                    session,
                    client,
                    lote,
                    args.forcar,
                    args.max_tentativas,
                    interpretar_anos(args.prioridade) if args.prioridade else None,
                    args.limite_minutos * 60 if args.limite_minutos else None,
                )
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
    if resumo["parado_por_tempo"]:
        print(f"Limite de tempo atingido: {resumo['a_tentar']} itens continuam na próxima execução")
    # 1 = algum item falhou nesta ou em outra execução do lote; parar pelo limite de tempo
    # com itens pendentes é o andamento normal da carga inicial (0)
    return 1 if resumo["falha"] else 0


if __name__ == "__main__":
    sys.exit(main())
