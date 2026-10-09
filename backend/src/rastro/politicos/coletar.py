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
from collections.abc import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from rastro.coletores.base import ColetaParcial, novo_cliente
from rastro.coletores.siconfi_lote import interpretar_anos
from rastro.db import get_sessionmaker
from rastro.fontes import executar_com_esperas
from rastro.politicos import camara, gestoes, senado, transparencia, tse
from rastro.politicos.modelos import DEPUTADO_FEDERAL, SENADOR, PolPolitico

log = logging.getLogger(__name__)
FONTES = ("camara", "senado", "emendas", "emendas-api", "tse", "prefeitos")
# "prefeitos" (eleições de prefeito 2020 e 2024, ADR-0018) só roda quando pedida
PADRAO = ("camara", "senado", "emendas", "emendas-api", "tse")


def _tentar(erros: list[str], rotulo: str, funcao, *args) -> int:
    try:
        return funcao(*args)
    except Exception as exc:  # uma falha não interrompe o restante da coleta
        log.warning("%s: %s", rotulo, exc)
        erros.append(f"{rotulo}: {type(exc).__name__}: {exc}")
        return 0


def cliente_da_fonte(
    fonte: str, base: Callable[[], httpx.Client] | None = None
) -> Callable[[], httpx.Client]:
    """Fábrica de clientes HTTP da fonte, usada em cada tentativa da coleta.

    A API do Portal da Transparência exige o cabeçalho `chave-api-dados` em toda consulta:
    cada cliente das emendas já sai com ele. Antes, a chave ia para um cliente descartado e
    as consultas saíam sem ela ("Chave de API não informada", 401).
    """
    base = base or novo_cliente
    if fonte != "emendas-api":
        return base

    def com_chave() -> httpx.Client:
        client = base()
        transparencia.preparar_cliente(client)
        return client

    return com_chave


def coletor_camara(uf: str, anos: list[int]):
    def coletar(session: Session, client: httpx.Client) -> int:
        erros: list[str] = []
        mapa = camara.coletar_deputados(session, client, uf)
        total = len(mapa)
        for id_camara, pid in sorted(mapa.items()):
            total += _tentar(
                erros,
                f"histórico {id_camara}",
                camara.coletar_historico,
                session,
                client,
                id_camara,
                pid,
            )
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
        from rastro.politicos import vinculo

        nomes = vinculo.universo(client)
        autores, recusados = vinculo.autores_confirmaveis(session, uf, nomes)
        if recusados:
            log.info("autores sem vínculo confirmável: %s", recusados)
        excecoes = vinculo.excecoes_por_texto(session)
        r = transparencia.coletar_arquivo(session, client, uf, min(anos), autores, excecoes)
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


def coletor_prefeitos(uf: str):
    """Eleições de prefeito (ordinária e suplementares) de 2020 e 2024, com prefeito e vice."""

    def coletar(session: Session, client: httpx.Client) -> int:
        from rastro.models import Municipio

        codigos = set(session.scalars(select(Municipio.cod_ibge).where(Municipio.uf == uf)))
        if not codigos:
            raise RuntimeError("Tabela de municípios vazia: rode `rastro coletar ibge-municipios`.")
        total = 0
        for ano in gestoes.MANDATOS:
            r = gestoes.coletar(session, client, ano, uf, codigos)
            log.info("TSE prefeitos %s: %s", ano, r)
            total += r["eleicoes"]
        return total

    return coletar


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rastro politicos", description=__doc__.split("\n\n")[0])
    p.add_argument("--uf", default="SP")
    p.add_argument("--anos", help="anos de atuação, ex.: 2023-2026 (câmara, senado, emendas)")
    p.add_argument("--fontes", nargs="+", choices=FONTES, default=list(PADRAO))
    p.add_argument(
        "--eleicoes",
        default="2022,2024,2026",
        help="anos de eleição do TSE (padrão: 2022,2024,2026)",
    )
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not args.anos and set(args.fontes) - {"tse", "prefeitos"}:
        p.error("--anos é obrigatório para câmara, senado e emendas")
    uf, anos = args.uf.upper(), interpretar_anos(args.anos) if args.anos else []

    coletores = {
        "camara": ("pol-camara", coletor_camara),
        "senado": ("pol-senado", coletor_senado),
        "emendas": ("pol-emendas", coletor_emendas_arquivo),
        "emendas-api": ("pol-emendas", coletor_emendas),
        "tse": ("pol-tse", lambda uf, _anos: coletor_tse(uf, interpretar_anos(args.eleicoes))),
        "prefeitos": ("pol-tse-prefeitos", lambda uf, _anos: coletor_prefeitos(uf)),
    }
    status = 0
    with get_sessionmaker()() as session:
        for fonte in args.fontes:
            nome, fabrica = coletores[fonte]
            if fonte == "emendas-api":
                print(f"emendas: acesso por {transparencia.modo_de_acesso()}")
            coleta = executar_com_esperas(session, nome, fabrica(uf, anos), cliente_da_fonte(fonte))
            print(f"{nome}: {coleta.status} ({coleta.registros or 0} registros)")
            if coleta.erro:
                print(coleta.erro, file=sys.stderr)
            if coleta.status != "sucesso":
                status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
