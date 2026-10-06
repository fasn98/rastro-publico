import argparse
import logging
import sys

from rastro.coletores import COLETORES, siconfi_demonstrativos
from rastro.coletores.base import executar, novo_cliente
from rastro.db import get_sessionmaker


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["siconfi-lote"]:
        from rastro.coletores import siconfi_lote

        return siconfi_lote.main(argv[1:])
    if argv[:1] == ["politicos"]:
        from rastro.politicos import coletar

        return coletar.main(argv[1:])

    parser = argparse.ArgumentParser(prog="rastro")
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("coletar", help="executa coletores")
    p.add_argument("fontes", nargs="*", help="fontes a coletar (padrão: todas)")
    sub.add_parser("fontes", help="lista as fontes disponíveis")
    sub.add_parser(
        "verificar-respostas",
        help="recalcula o SHA-256 de todas as respostas brutas arquivadas",
    )
    r = sub.add_parser("ranking", help="calcula e grava o Ranking Fiscal de uma UF")
    r.add_argument("--uf", required=True)
    sub.add_parser(
        "politicos",
        help="coleta deputados federais, senadores e emendas (ver `rastro politicos --help`)",
        add_help=False,
    )
    sub.add_parser(
        "siconfi-lote",
        help="coleta RREO/RGF em lote, retomável (ver `rastro siconfi-lote --help`)",
        add_help=False,
    )

    d = sub.add_parser(
        "siconfi-demonstrativos",
        help="coleta RREO e RGF do SICONFI (requer `rastro coletar siconfi-entes` antes)",
    )
    d.add_argument("--exercicio", type=int, nargs="+", required=True)
    alvo = d.add_argument_group("entes (informe ao menos um filtro, ou --todos)")
    alvo.add_argument("--ente", type=int, nargs="+", help="código IBGE do ente")
    alvo.add_argument("--uf", nargs="+", help="ex.: SP RJ")
    alvo.add_argument("--esfera", nargs="+", choices=["U", "E", "D", "M"])
    alvo.add_argument("--todos", action="store_true", help="todos os 5.598 entes")
    d.add_argument("--forcar", action="store_true", help="baixa de novo mesmo sem retificação")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.comando == "fontes":
        print("\n".join(COLETORES))
        return 0

    if args.comando == "verificar-respostas":
        return _verificar_respostas()

    if args.comando == "ranking":
        from rastro import ranking

        met = ranking.carregar_metodologia()
        with get_sessionmaker()() as session:
            itens = ranking.calcular(session, args.uf, met)
        com_nota = sum(1 for i in itens if i["nota"] is not None)
        print(
            f"Ranking {args.uf.upper()} v{met.versao} ({met.hash}), exercícios "
            f"{met.exercicios}: {com_nota}/{len(itens)} municípios com nota"
        )
        # distribuição da transparência (indicador provisório: rever se quase todos = 100%)
        notas_t = [
            i["componentes"]["transparencia"]["nota"]
            for i in itens
            if i["componentes"]["transparencia"]["nota"] is not None
        ]
        if notas_t:
            print(f"Transparência ({len(notas_t)} municípios com extrato coletado):")
            faixas_t = [(1.0, 1.0, "100%"), (0.75, 0.9999, "75–99%"), (0.5, 0.7499, "50–74%"),
                        (0.0, 0.4999, "0–49%")]  # fmt: skip
            for de, ate, rotulo in faixas_t:
                n = sum(1 for v in notas_t if de <= v <= ate)
                print(f"  {rotulo:>7}: {n:4d} ({n / len(notas_t):.0%})")
        return 0

    if args.comando == "siconfi-demonstrativos":
        return _demonstrativos(parser, args)

    desconhecidas = set(args.fontes) - set(COLETORES)
    if desconhecidas:
        parser.error(f"fonte(s) desconhecida(s): {', '.join(sorted(desconhecidas))}")

    falhas = 0
    with novo_cliente() as client, get_sessionmaker()() as session:
        for fonte in args.fontes or list(COLETORES):
            coleta = executar(session, fonte, COLETORES[fonte], client)
            print(f"{fonte}: {coleta.status} ({coleta.registros or 0} registros)")
            if coleta.erro:
                print(f"  erro: {coleta.erro}", file=sys.stderr)
                falhas += 1
    return 1 if falhas else 0


def _demonstrativos(parser: argparse.ArgumentParser, args) -> int:
    if not (args.ente or args.uf or args.esfera or args.todos):
        parser.error("informe --ente, --uf, --esfera ou --todos")
    with novo_cliente() as client, get_sessionmaker()() as session:
        entes = siconfi_demonstrativos.selecionar_entes(session, args.ente, args.uf, args.esfera)
        if not entes:
            print(
                "Nenhum ente encontrado. Rode `rastro coletar siconfi-entes` antes.",
                file=sys.stderr,
            )
            return 1
        if args.ente:
            faltando = set(args.ente) - {e.cod_ibge for e in entes}
            if faltando:
                print(f"Entes não cadastrados: {sorted(faltando)}", file=sys.stderr)
        print(f"{len(entes)} ente(s), exercício(s) {args.exercicio}")
        coletor = siconfi_demonstrativos.coletor(entes, args.exercicio, args.forcar)
        coleta = executar(session, "siconfi-demonstrativos", coletor, client)
    print(f"siconfi-demonstrativos: {coleta.status} ({coleta.registros or 0} linhas)")
    if coleta.erro:
        print(coleta.erro, file=sys.stderr)
    return 0 if coleta.status == "sucesso" else 1


def _verificar_respostas() -> int:
    from sqlalchemy import func, select

    from rastro.coletores.arquivo import ler_payload
    from rastro.models import PayloadBruto, RespostaBruta

    with get_sessionmaker()() as session:
        total = ruins = 0
        for p in session.scalars(select(PayloadBruto).execution_options(yield_per=200)):
            total += 1
            try:
                ler_payload(p)
            except ValueError as exc:
                ruins += 1
                print(exc, file=sys.stderr)
        respostas = session.scalar(select(func.count()).select_from(RespostaBruta))
    print(f"{respostas} respostas, {total} payloads distintos verificados, {ruins} com problema")
    return 1 if ruins else 0


if __name__ == "__main__":
    sys.exit(main())
