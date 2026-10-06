"""Coleta do módulo de políticos.

    uv run rastro politicos --uf SP --anos 2023-2026
    uv run rastro politicos --uf SP --anos 2025 --fontes senado

Cada fonte vira uma execução na tabela `coleta` (pol-camara, pol-senado, pol-emendas), e
toda resposta recebida fica no arquivo de respostas brutas. Falha em um deputado ou ano
não interrompe os outros: a coleta fica `parcial`, com os erros registrados.
"""

import argparse
import logging
import sys

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from rastro.coletores.base import ColetaParcial, executar, novo_cliente
from rastro.coletores.siconfi_lote import interpretar_anos
from rastro.db import get_sessionmaker
from rastro.politicos import camara, senado, transparencia
from rastro.politicos.modelos import DEPUTADO_FEDERAL, SENADOR, PolPolitico

log = logging.getLogger(__name__)
FONTES = ("camara", "senado", "emendas")


def _tentar(erros: list[str], rotulo: str, funcao, *args) -> int:
    try:
        return funcao(*args)
    except Exception as exc:  # uma falha não interrompe o restante da coleta
        log.warning("%s: %s", rotulo, exc)
        erros.append(f"{rotulo}: {type(exc).__name__}: {exc}")
        return 0


def coletor_camara(uf: str, anos: list[int]):
    def coletar(session: Session, client: httpx.Client) -> int:
        erros: list[str] = []
        mapa = camara.coletar_deputados(session, client, uf)
        total = len(mapa)
        for ano in anos:
            for id_camara, pid in sorted(mapa.items()):
                total += _tentar(
                    erros,
                    f"proposições {id_camara}/{ano}",
                    camara.coletar_proposicoes,
                    session,
                    client,
                    id_camara,
                    pid,
                    ano,
                )
            total += _tentar(
                erros, f"votos {ano}", camara.coletar_votos, session, client, ano, mapa
            )
            total += _tentar(
                erros, f"presenças {ano}", camara.coletar_presencas, session, client, ano, mapa
            )
        if erros:
            raise ColetaParcial(total, erros)
        return total

    return coletar


def coletor_senado(uf: str, anos: list[int]):
    def coletar(session: Session, client: httpx.Client) -> int:
        erros: list[str] = []
        mapa = senado.coletar_senadores(session, client, uf)
        total = len(mapa)
        for codigo, pid in sorted(mapa.items()):
            total += _tentar(
                erros, f"comissões {codigo}", senado.coletar_comissoes, session, client, codigo, pid
            )
            for ano in anos:
                for rotulo, funcao in (
                    ("matérias", senado.coletar_materias),
                    ("votações", senado.coletar_votacoes),
                ):
                    total += _tentar(
                        erros, f"{rotulo} {codigo}/{ano}", funcao, session, client, codigo, pid, ano
                    )
        if erros:
            raise ColetaParcial(total, erros)
        return total

    return coletar


def coletor_emendas(uf: str, anos: list[int]):
    """Emendas dos deputados federais e senadores da UF já gravados (rode camara/senado antes)."""

    def coletar(session: Session, client: httpx.Client) -> int:
        transparencia.verificar_acesso(client, anos[0])  # 401 -> falha clara, nada gravado
        erros: list[str] = []
        municipios = transparencia.municipios_por_nome(session)
        politicos = session.execute(
            select(PolPolitico.id, PolPolitico.nome).where(
                PolPolitico.uf == uf, PolPolitico.cargo.in_([DEPUTADO_FEDERAL, SENADOR])
            )
        ).all()
        total = 0
        for pid, nome in sorted(politicos, key=lambda p: p.nome):
            for ano in anos:
                total += _tentar(
                    erros,
                    f"emendas {nome}/{ano}",
                    transparencia.coletar_emendas_autor,
                    session,
                    client,
                    nome,
                    pid,
                    ano,
                    municipios,
                )
        if erros:
            raise ColetaParcial(total, erros)
        return total

    return coletar


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rastro politicos", description=__doc__.split("\n\n")[0])
    p.add_argument("--uf", default="SP")
    p.add_argument("--anos", required=True, help="ex.: 2023-2026")
    p.add_argument("--fontes", nargs="+", choices=FONTES, default=list(FONTES))
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    uf, anos = args.uf.upper(), interpretar_anos(args.anos)

    coletores = {
        "camara": ("pol-camara", coletor_camara),
        "senado": ("pol-senado", coletor_senado),
        "emendas": ("pol-emendas", coletor_emendas),
    }
    status = 0
    with get_sessionmaker()() as session:
        for fonte in args.fontes:
            nome, fabrica = coletores[fonte]
            with novo_cliente() as client:
                if fonte == "emendas":
                    print(f"emendas: acesso por {transparencia.preparar_cliente(client)}")
                coleta = executar(session, nome, fabrica(uf, anos), client)
            print(f"{nome}: {coleta.status} ({coleta.registros or 0} registros)")
            if coleta.erro:
                print(coleta.erro, file=sys.stderr)
            if coleta.status != "sucesso":
                status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
