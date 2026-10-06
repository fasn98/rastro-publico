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
from rastro.politicos import camara, senado, transparencia, tse
from rastro.politicos.modelos import DEPUTADO_FEDERAL, SENADOR, PolPolitico

log = logging.getLogger(__name__)
FONTES = ("camara", "senado", "emendas", "emendas-api", "tse")


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
            total += _tentar(
                erros, f"cota {ano}", camara.coletar_cota, session, client, ano, uf, mapa
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


def coletor_emendas_arquivo(uf: str, anos: list[int]):
    """Emendas do arquivo em lote do Portal (sem chave), com o código IBGE oficial."""

    def coletar(session: Session, client: httpx.Client) -> int:
        autores = {
            transparencia.normalizar_nome(nome): pid
            for pid, nome in session.execute(
                select(PolPolitico.id, PolPolitico.nome).where(
                    PolPolitico.uf == uf, PolPolitico.cargo.in_([DEPUTADO_FEDERAL, SENADOR])
                )
            )
        }
        r = transparencia.coletar_arquivo(session, client, uf, min(anos), autores)
        log.info("emendas (arquivo): %s", r)
        return r["linhas"]

    return coletar


def coletor_emendas(uf: str, anos: list[int]):
    """Emendas pela API (exige chave), por autor: deputados e senadores da UF já gravados."""

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


def coletor_tse(uf: str, eleicoes: list[int]):
    """Eleitos do TSE (2024: prefeitos e vereadores; 2022: governador e dep. estaduais)."""

    def coletar(session: Session, client: httpx.Client) -> int:
        from rastro.models import Municipio

        codigos = set(session.scalars(select(Municipio.cod_ibge).where(Municipio.uf == uf)))
        if not codigos:
            raise RuntimeError("Tabela de municípios vazia: rode `rastro coletar ibge-municipios`.")
        total = 0
        for ano in eleicoes:
            r = tse.coletar_eleitos(session, client, ano, uf, codigos)
            log.info("TSE %s: %s", ano, r)
            total += r["eleitos"]
        return total

    return coletar


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rastro politicos", description=__doc__.split("\n\n")[0])
    p.add_argument("--uf", default="SP")
    p.add_argument("--anos", help="anos de atuação, ex.: 2023-2026 (câmara, senado, emendas)")
    p.add_argument("--fontes", nargs="+", choices=FONTES, default=list(FONTES))
    p.add_argument(
        "--eleicoes", default="2022,2024", help="anos de eleição do TSE (padrão: 2022,2024)"
    )
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not args.anos and set(args.fontes) - {"tse"}:
        p.error("--anos é obrigatório para câmara, senado e emendas")
    uf, anos = args.uf.upper(), interpretar_anos(args.anos) if args.anos else []

    coletores = {
        "camara": ("pol-camara", coletor_camara),
        "senado": ("pol-senado", coletor_senado),
        "emendas": ("pol-emendas", coletor_emendas_arquivo),
        "emendas-api": ("pol-emendas", coletor_emendas),
        "tse": ("pol-tse", lambda uf, _anos: coletor_tse(uf, interpretar_anos(args.eleicoes))),
    }
    status = 0
    with get_sessionmaker()() as session:
        for fonte in args.fontes:
            nome, fabrica = coletores[fonte]
            with novo_cliente() as client:
                if fonte == "emendas-api":
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
