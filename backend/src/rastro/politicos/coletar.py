"""Coleta do módulo de políticos.

    uv run rastro politicos --uf SP --anos 2023-2026
    uv run rastro politicos --uf SP --anos 2025 --fontes senado
    uv run rastro politicos --uf SP AC --anos 2023-2026 --fontes emendas
    uv run rastro politicos --uf TODAS --fontes tse

Cada fonte vira uma execução na tabela `coleta` (pol-camara, pol-senado, pol-emendas), e
toda resposta recebida fica no arquivo de respostas brutas. As emendas do arquivo em lote
saem numa execução só para todas as UFs pedidas; as outras fontes, uma por UF. Falha em um
deputado ou ano não interrompe os outros: a coleta fica `parcial`, com os erros registrados.
"""

import argparse
import logging
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from rastro.coletores.base import ColetaParcial, novo_cliente
from rastro.coletores.siconfi_lote import TODAS, interpretar_anos
from rastro.config import get_settings
from rastro.db import get_sessionmaker
from rastro.fontes import executar_com_esperas
from rastro.politicos import camara, gestoes, reuso, senado, transparencia, tse
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


class Prazo:
    """Limite de tempo da coleta dos políticos (RASTRO_POLITICOS_LIMITE_MIN; 0 = sem limite).

    Ao passar do limite, a coleta para antes do próximo item (deputado, ano, UF ou fonte):
    o que já foi gravado fica, e a execução sai `parcial` com o motivo.
    """

    def __init__(self, minutos: float = 0, relogio: Callable[[], float] = time.monotonic):
        self.minutos, self._relogio = minutos, relogio
        self._fim = relogio() + minutos * 60 if minutos > 0 else None

    def esgotado(self) -> bool:
        return self._fim is not None and self._relogio() >= self._fim

    @property
    def motivo(self) -> str:
        return f"limite de tempo de {self.minutos:g} min atingido"


SEM_PRAZO = Prazo()


class _PrazoEsgotado(Exception):
    pass


def coletor_camara(ufs: str | list[str], anos: list[int], prazo: Prazo = SEM_PRAZO, hoje=None):
    """Deputados federais das UFs, numa passada só.

    A lista de deputados vem por UF; os arquivos anuais (votos, presenças e cota) são
    nacionais e são baixados uma vez para todas as UFs. Nos anos fechados, um arquivo já
    baixado na semana, arquivado e que cobriu todas as UFs pedidas não é baixado de novo
    (`reuso`); as proposições do deputado no ano fechado, idem.
    """
    ufs = [ufs] if isinstance(ufs, str) else list(ufs)

    def coletar(session: Session, client: httpx.Client) -> int:
        erros: list[str] = []
        mapa: dict[int, int] = {}
        for uf in ufs:
            mapa.update(camara.coletar_deputados(session, client, uf))
        total = len(mapa)

        def tentar(rotulo: str, funcao, *args) -> None:
            nonlocal total
            if prazo.esgotado():
                raise _PrazoEsgotado
            total += _tentar(erros, rotulo, funcao, session, client, *args)

        try:
            for id_camara, pid in sorted(mapa.items()):
                tentar(f"histórico {id_camara}", camara.coletar_historico, id_camara, pid)
            for ano in anos:
                fechado = reuso.ano_fechado(ano, hoje)
                for id_camara, pid in sorted(mapa.items()):
                    if fechado and reuso.url_recente(
                        session, camara.url_proposicoes(id_camara, ano)
                    ):
                        continue
                    rotulo = f"proposições {id_camara}/{ano}"
                    tentar(rotulo, camara.coletar_proposicoes, id_camara, pid, ano)
                for tipo, rotulo, funcao, extra in (
                    ("votos", "votos", camara.coletar_votos, ()),
                    ("presencas", "presenças", camara.coletar_presencas, ()),
                    ("cota", "cota", camara.coletar_cota, (ufs,)),
                ):
                    if fechado and set(ufs) <= reuso.ufs_com_arquivo_recente(session, tipo, ano):
                        log.info("%s %s: arquivo da semana reaproveitado", rotulo, ano)
                        continue
                    tentar(f"{rotulo} {ano}", funcao, ano, *extra, mapa)
        except _PrazoEsgotado:
            erros.append(prazo.motivo)
        if erros:
            raise ColetaParcial(total, erros)
        return total

    return coletar


def coletor_senado(uf: str, anos: list[int], prazo: Prazo = SEM_PRAZO):
    def coletar(session: Session, client: httpx.Client) -> int:
        erros: list[str] = []
        mapa = senado.coletar_senadores(session, client, uf)
        total = len(mapa)
        for codigo, pid in sorted(mapa.items()):
            if prazo.esgotado():
                erros.append(prazo.motivo)
                break
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


def coletor_emendas_arquivo(ufs: list[str], anos: list[int]):
    """Emendas do arquivo em lote do Portal (sem chave), com o código IBGE oficial.

    Uma passada para todas as UFs: a gravação substitui as linhas do arquivo por inteiro.
    """

    def coletar(session: Session, client: httpx.Client) -> int:
        from rastro.politicos import vinculo

        nomes = vinculo.universo(client)
        autores = {}
        for uf in ufs:
            da_uf, recusados = vinculo.autores_confirmaveis(session, uf, nomes)
            autores.update(da_uf)
            if recusados:
                log.info("autores de %s sem vínculo confirmável: %s", uf, recusados)
        excecoes = vinculo.excecoes_por_texto(session)
        r = transparencia.coletar_arquivo(session, client, ufs, min(anos), autores, excecoes)
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


def coletor_tse(uf: str, eleicoes: list[int], hoje: datetime | None = None):
    """Eleitos do TSE (2024: prefeitos e vereadores; 2022: governador e dep. estaduais).

    A eleição do ano corrente é sempre baixada; as anteriores, só se os eleitos da UF não
    vierem de um download da semana, ainda arquivado (`reuso`).
    """

    def coletar(session: Session, client: httpx.Client) -> int:
        from rastro.models import Municipio

        codigos = set(session.scalars(select(Municipio.cod_ibge).where(Municipio.uf == uf)))
        if not codigos:
            raise RuntimeError("Tabela de municípios vazia: rode `rastro coletar ibge-municipios`.")
        ano_corrente = (hoje or datetime.now(UTC)).year
        total = 0
        for ano in eleicoes:
            if ano < ano_corrente and reuso.tse_recente(session, ano, uf):
                log.info("TSE %s %s: arquivo da semana reaproveitado", ano, uf)
                continue
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
    p.add_argument("--uf", nargs="+", default=["SP"], help="ex.: SP AC; TODAS = as 27 UFs")
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
    ufs = sorted({u.upper() for u in args.uf})
    if ufs == [TODAS]:
        ufs = sorted(transparencia.NOMES_UF)
    elif desconhecidas := set(ufs) - set(transparencia.NOMES_UF):
        p.error(f"UF desconhecida: {', '.join(sorted(desconhecidas))}")
    anos = interpretar_anos(args.anos) if args.anos else []

    prazo = Prazo(get_settings().politicos_limite_min)
    coletores = {
        "camara": ("pol-camara", lambda alvo, anos: coletor_camara(alvo, anos, prazo)),
        "senado": ("pol-senado", lambda alvo, anos: coletor_senado(alvo, anos, prazo)),
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
            # câmara e emendas do arquivo: uma passada para todas as UFs; demais: uma por UF
            if fonte in ("camara", "emendas"):
                alvos = [(ufs, "/".join(ufs))]
            else:
                alvos = [(u, u) for u in ufs]
            for alvo, rotulo in alvos:
                if prazo.esgotado():
                    print(f"{nome} {rotulo}: não coletada ({prazo.motivo})", file=sys.stderr)
                    status = 1
                    continue
                coleta = executar_com_esperas(
                    session, nome, fabrica(alvo, anos), cliente_da_fonte(fonte)
                )
                print(f"{nome} {rotulo}: {coleta.status} ({coleta.registros or 0} registros)")
                if coleta.erro:
                    print(coleta.erro, file=sys.stderr)
                if coleta.status != "sucesso":
                    status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
