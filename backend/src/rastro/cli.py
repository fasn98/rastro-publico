import argparse
import logging
import sys

from rastro.coletores import COLETORES
from rastro.coletores.base import executar, novo_cliente
from rastro.db import get_sessionmaker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rastro")
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("coletar", help="executa coletores")
    p.add_argument("fontes", nargs="*", help="fontes a coletar (padrão: todas)")
    sub.add_parser("fontes", help="lista as fontes disponíveis")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.comando == "fontes":
        print("\n".join(COLETORES))
        return 0

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


if __name__ == "__main__":
    sys.exit(main())
