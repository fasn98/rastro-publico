"""Relatório de uma UF antes de liberar os políticos dela (só leitura).

    cd backend && uv run python scripts/relatorio_uf.py --uf SC [--sem-fonte] [--json saida.json]

O script pede a connection string do banco (sem eco na tela, como o `read -s`) e não usa
DATABASE_URL, RASTRO_DATABASE_URL nem o `.env`: no Replit, essas variáveis podem apontar
para o banco de desenvolvimento. A primeira linha mostra o servidor e o banco conectados
(sem a senha), para conferir que é o de produção.

Imprime só contagens e situações, nunca nomes, CPFs ou outros dados pessoais. Os motivos que
trazem nomes de pessoas (exceções de emendas, candidatos do 2º turno) saem só contados.

- Portão fiscal e portão de políticos da UF, com o mesmo código do `rastro portao`
  (`rastro.portao.avaliar_uf` e `rastro.politicos.portao.avaliar_uf`). A conferência
  fiscal com a fonte baixa de novo 3 RREOs sorteados do SICONFI (o sorteio é o do dia, por
  isso os entes podem diferir dos do manifesto); `--sem-fonte` pula essa etapa.
- Políticos por fonte e cargo; eleitos do TSE por eleição e cargo; pendências do TSE por
  eleição, cargo e tipo (`segundo_turno` = 2º turno ainda pendente no arquivo do TSE).
- Emendas com destino em município da UF e emendas de parlamentares da UF no portal:
  total, ligadas pelo nome, por exceção aprovada e sem vínculo (separando as de autor com o
  mesmo nome de um parlamentar da UF no portal, que ficam sem link por código de autor
  ambíguo, homônimo ou fora do mandato, das de bancadas, comissões e parlamentares de
  outras UFs).
- Última coleta de cada fonte de políticos na UF (`pol_coleta_uf`).

Só leitura: a conexão abre com `default_transaction_read_only=on`, e o PostgreSQL recusa
qualquer escrita. A conferência com o SICONFI usa um cliente HTTP sem arquivamento.
"""

import argparse
import getpass
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from rastro.models import Municipio
from rastro.politicos import portao as portao_politicos
from rastro.politicos.modelos import (
    PolColetaUf,
    PolEmenda,
    PolPendencia,
    PolPolitico,
)
from rastro.politicos.transparencia import normalizar_nome

FONTES_COLETA = ("pol-camara", "pol-senado", "pol-tse", "pol-emendas", "pol-tse-prefeitos")


def _motivos_sem_nomes(motivos: list[str]) -> list[str]:
    """Os motivos de exceção citam o nome do autor como está na fonte: saem contados."""
    excecoes = [m for m in motivos if m.startswith("exceção aprovada")]
    outros = [m for m in motivos if not m.startswith("exceção aprovada")]
    if excecoes:
        outros.append(f"{len(excecoes)} exceção(ões) aprovada(s) de emenda sem linha no arquivo")
    return outros


def portao_fiscal(session: Session, uf: str, com_fonte: bool) -> dict:
    from rastro import portao
    from rastro import ranking as rk

    exercicios = rk.carregar_metodologia().exercicios
    if not com_fonte:
        entes = portao._entes(session, uf)
        comp = portao.completude(session, entes, exercicios)
        return {
            "conferencia_com_a_fonte": "pulada (--sem-fonte)",
            "completude": {k: v for k, v in comp.items() if k != "exemplos"},
        }
    with httpx.Client(timeout=60) as client:  # sem arquivamento: nada é gravado
        r = portao.avaliar_uf(session, client, uf, exercicios, datetime.now(UTC).date())
    return {
        "aprovada": r["aprovada"],
        "motivos": r["motivos"],
        "completude": {k: v for k, v in (r.get("completude") or {}).items() if k != "exemplos"},
        "arquivo_bruto": {
            "conferidas": (r.get("arquivo_bruto") or {}).get("conferidas"),
            "divergentes": len((r.get("arquivo_bruto") or {}).get("divergentes", [])),
        },
        "sorteados": [
            {k: s[k] for k in ("cod_ibge", "relatorio", "situacao", "ok")}
            for s in r.get("sorteados") or []
        ],
    }


def politicos(session: Session, uf: str) -> dict:
    por_fonte_cargo = {
        f"{fonte}/{cargo}": {"total": total, "em_exercicio": em_ex}
        for fonte, cargo, total, em_ex in session.execute(
            select(
                PolPolitico.fonte,
                PolPolitico.cargo,
                func.count(),
                func.count().filter(PolPolitico.em_exercicio.is_(True)),
            )
            .where(PolPolitico.uf == uf, PolPolitico.fonte.in_(("camara", "senado")))
            .group_by(PolPolitico.fonte, PolPolitico.cargo)
            .order_by(PolPolitico.fonte, PolPolitico.cargo)
        )
    }
    eleitos = defaultdict(dict)
    for ano, cargo, n in session.execute(
        select(PolPolitico.eleicao_ano, PolPolitico.cargo, func.count())
        .where(PolPolitico.uf == uf, PolPolitico.fonte == "tse")
        .group_by(PolPolitico.eleicao_ano, PolPolitico.cargo)
        .order_by(PolPolitico.eleicao_ano, PolPolitico.cargo)
    ):
        eleitos[str(ano)][cargo] = n
    municipios = session.scalar(
        select(func.count()).select_from(Municipio).where(Municipio.uf == uf)
    )
    com_prefeito_2024 = session.scalar(
        select(func.count(func.distinct(PolPolitico.cod_ibge))).where(
            PolPolitico.uf == uf,
            PolPolitico.fonte == "tse",
            PolPolitico.eleicao_ano == 2024,
            PolPolitico.cargo == "prefeito",
        )
    )
    pendencias = Counter(
        f"{ano}/{cargo}/{tipo}"
        for ano, cargo, tipo in session.execute(
            select(PolPendencia.eleicao_ano, PolPendencia.cargo, PolPendencia.tipo).where(
                PolPendencia.uf == uf, PolPendencia.fonte == "tse"
            )
        )
    )
    segundo_turno = sorted(k for k in pendencias if k.endswith("/segundo_turno"))
    return {
        "camara_e_senado": por_fonte_cargo,
        "eleitos_tse": dict(eleitos),
        "municipios_da_uf": municipios,
        "municipios_com_prefeito_eleito_2024": com_prefeito_2024,
        "pendencias_tse": dict(sorted(pendencias.items())),
        "segundo_turno_pendente": segundo_turno,
    }


def _resumo_emendas(linhas: list[tuple], nomes_da_uf: set[str], ambiguos: set[str]) -> dict:
    """linhas: (vinculo, politico_id, nome_autor, codigo_autor, fonte_dados)."""
    c = Counter()
    for vinculo, pid, nome, _codigo, fonte in linhas:
        c[f"fonte_{fonte}"] += 1
        if vinculo == "excecao":
            c["por_excecao"] += 1
        elif pid is not None:
            c["ligadas_pelo_nome"] += 1
        elif nome and normalizar_nome(nome) in ambiguos:
            c["sem_vinculo_codigo_de_autor_ambiguo"] += 1
        elif nome and normalizar_nome(nome) in nomes_da_uf:
            c["sem_vinculo_homonimo_ou_fora_do_mandato"] += 1
        else:
            c["sem_vinculo_outros_autores"] += 1
    c["total"] = len(linhas)
    return dict(sorted(c.items()))


def emendas(session: Session, uf: str) -> dict:
    nomes_da_uf = {
        normalizar_nome(n)
        for (n,) in session.execute(
            select(PolPolitico.nome).where(
                PolPolitico.uf == uf, PolPolitico.fonte.in_(("camara", "senado"))
            )
        )
    }
    cols = (
        PolEmenda.vinculo,
        PolEmenda.politico_id,
        PolEmenda.nome_autor,
        PolEmenda.codigo_autor,
        PolEmenda.fonte_dados,
    )
    todas = session.execute(select(*cols, PolEmenda.cod_ibge_destino)).all()
    # regra 4 de vinculo.py: o mesmo nome com mais de um "Código do Autor" em todo o
    # arquivo deixa todas as emendas daquele nome sem link
    codigos: dict[str, set] = defaultdict(set)
    for _v, _pid, nome, codigo, _f, _cod in todas:
        if nome and normalizar_nome(nome) in nomes_da_uf:
            codigos[normalizar_nome(nome)].add(codigo)
    ambiguos = {n for n, cs in codigos.items() if len(cs) > 1}
    cods_da_uf = set(session.scalars(select(Municipio.cod_ibge).where(Municipio.uf == uf)))
    ids_da_uf = set(session.scalars(select(PolPolitico.id).where(PolPolitico.uf == uf)))
    destino = [x[:5] for x in todas if x[5] in cods_da_uf]
    autoria = [
        x[:5]
        for x in todas
        if x[1] in ids_da_uf or (x[1] is None and x[2] and normalizar_nome(x[2]) in nomes_da_uf)
    ]
    return {
        "destino_em_municipio_da_uf": _resumo_emendas(destino, nomes_da_uf, ambiguos),
        "municipios_da_uf_com_emenda": len({x[5] for x in todas if x[5] in cods_da_uf}),
        "de_parlamentares_da_uf_no_portal": _resumo_emendas(autoria, nomes_da_uf, ambiguos),
        "autores_da_uf_com_codigo_de_autor_ambiguo": len(ambiguos),
    }


def coletas(session: Session, uf: str) -> dict:
    r = {}
    for fonte in FONTES_COLETA:
        u = session.scalar(
            select(PolColetaUf)
            .where(PolColetaUf.fonte == fonte, PolColetaUf.uf == uf)
            .order_by(PolColetaUf.id.desc())
            .limit(1)
        )
        r[fonte] = (
            {"status": u.status, "registrada_em": u.registrada_em.isoformat()}
            if u
            else "ainda não coletada"
        )
    return r


def relatorio(session: Session, uf: str, com_fonte: bool = True) -> dict:
    uf = uf.upper()
    pol = portao_politicos.avaliar_uf(session, uf)
    return {
        "uf": uf,
        "gerado_em": datetime.now(UTC).isoformat(),
        "portao_fiscal": portao_fiscal(session, uf, com_fonte),
        "portao_politicos": {
            "aprovada": pol["aprovada"],
            "motivos": _motivos_sem_nomes(pol["motivos"]),
        },
        "politicos": politicos(session, uf),
        "emendas": emendas(session, uf),
        "ultima_coleta": coletas(session, uf),
    }


def _imprimir(r: dict, nivel: int = 0) -> None:
    for k, v in r.items():
        if isinstance(v, dict):
            print(f"{'  ' * nivel}{k}:")
            _imprimir(v, nivel + 1)
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            print(f"{'  ' * nivel}{k}:")
            for x in v:
                print(f"{'  ' * (nivel + 1)}- {x}")
        else:
            print(f"{'  ' * nivel}{k}: {v}")


def url_do_banco(texto: str) -> str:
    """Connection string como o Replit e o Neon entregam (`postgres://`, `postgresql://`)
    -> com o driver do projeto."""
    texto = texto.strip()
    for prefixo in ("postgres://", "postgresql://"):
        if texto.startswith(prefixo):
            return "postgresql+psycopg://" + texto[len(prefixo) :]
    return texto


def onde(url: str) -> str:
    """Servidor e banco, sem usuário nem senha."""
    u = make_url(url)
    return f"servidor={u.host} banco={u.database}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--uf", required=True)
    ap.add_argument("--sem-fonte", action="store_true", help="não confere 3 RREOs no SICONFI")
    ap.add_argument("--json", help="grava também o resultado neste arquivo")
    args = ap.parse_args(argv)
    url = url_do_banco(getpass.getpass("Connection string do banco (não aparece na tela): "))
    if not url:
        print("Nenhuma connection string informada.", file=sys.stderr)
        return 2
    engine = create_engine(url, connect_args={"options": "-c default_transaction_read_only=on"})
    print(f"Conectado a {onde(url)} (só leitura)")
    with Session(engine) as session:
        r = relatorio(session, args.uf, com_fonte=not args.sem_fonte)
    engine.dispose()
    _imprimir(r)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(r, f, ensure_ascii=False, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
