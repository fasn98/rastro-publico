"""Diagnóstico (só leitura) das emendas vindas da API do Portal (fonte_dados = 'api').

Pergunta: as 432 linhas da API atribuídas a parlamentares do RS (relatorio_uf.py, 22/11)
são sobras sem autor? As linhas da API só são apagadas pelo politico_id
(transparencia.coletar_emendas_autor), e a chave estrangeira é ON DELETE SET NULL: se o
político sai do banco, as emendas dele ficam com politico_id nulo e ninguém as apaga.

Imprime só contagens e datas, nunca nomes. Pede a connection string sem eco e abre a
conexão com default_transaction_read_only=on.
"""

import getpass
import sys
from collections import Counter

from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from rastro.models import Municipio
from rastro.politicos.modelos import PolEmenda, PolPolitico
from rastro.politicos.transparencia import normalizar_nome

UF = (sys.argv[1] if len(sys.argv) > 1 else "RS").upper()


def url_do_banco(texto: str) -> str:
    texto = texto.strip()
    for prefixo in ("postgres://", "postgresql://"):
        if texto.startswith(prefixo):
            return "postgresql+psycopg://" + texto[len(prefixo) :]
    return texto


url = url_do_banco(getpass.getpass("Connection string do banco (não aparece na tela): "))
engine = create_engine(url, connect_args={"options": "-c default_transaction_read_only=on"})
u = make_url(url)
print(f"Conectado a servidor={u.host} banco={u.database} (só leitura)")

with Session(engine) as s:
    ids_existentes = set(s.scalars(select(PolPolitico.id)))
    ids_uf = set(s.scalars(select(PolPolitico.id).where(PolPolitico.uf == UF)))
    nomes_uf = {
        normalizar_nome(n)
        for n in s.scalars(
            select(PolPolitico.nome).where(
                PolPolitico.uf == UF, PolPolitico.fonte.in_(("camara", "senado"))
            )
        )
    }
    uf_do_politico = dict(s.execute(select(PolPolitico.id, PolPolitico.uf)).all())
    cods_uf = set(s.scalars(select(Municipio.cod_ibge).where(Municipio.uf == UF)))
    cod_arquivo = set(
        s.scalars(select(PolEmenda.codigo_emenda).where(PolEmenda.fonte_dados == "arquivo"))
    )
    api = s.execute(
        select(
            PolEmenda.politico_id,
            PolEmenda.nome_autor,
            PolEmenda.ano,
            PolEmenda.vinculo,
            PolEmenda.codigo_emenda,
            PolEmenda.cod_ibge_destino,
            PolEmenda.uf_destino,
            PolEmenda.atualizado_em,
            PolEmenda.resposta_id,
        ).where(PolEmenda.fonte_dados == "api")
    ).all()

    def resumo(titulo, linhas):
        print(f"\n== {titulo}: {len(linhas)} linhas")
        if not linhas:
            return
        pid_nulo = [x for x in linhas if x.politico_id is None]
        print(f"  politico_id nulo (sem autor no banco): {len(pid_nulo)}")
        print(
            "  politico_id de político que existe: "
            f"{sum(1 for x in linhas if x.politico_id in ids_existentes)}"
        )
        print(f"  vinculo: {dict(Counter(x.vinculo for x in linhas))}")
        print(f"  por ano: {dict(sorted(Counter(x.ano for x in linhas).items()))}")
        datas = sorted(x.atualizado_em for x in linhas if x.atualizado_em)
        if datas:
            print(f"  gravadas entre {datas[0]:%d/%m/%Y %H:%M} e {datas[-1]:%d/%m/%Y %H:%M} UTC")
            print(
                "  por dia de gravação: "
                f"{dict(sorted(Counter(f'{d:%d/%m/%Y}' for d in datas).items()))}"
            )
        print(f"  respostas arquivadas distintas: {len({x.resposta_id for x in linhas})}")
        print(
            "  mesmo codigo_emenda também no arquivo do Portal (duplicadas): "
            f"{sum(1 for x in linhas if x.codigo_emenda in cod_arquivo)}"
        )
        print(
            "  destino em município da UF: "
            f"{sum(1 for x in linhas if x.cod_ibge_destino in cods_uf)}"
        )
        print(
            "  por UF de destino (uf_destino): "
            f"{dict(Counter(x.uf_destino for x in linhas).most_common(8))}"
        )

    print(f"\nTodas as linhas da API no banco: {len(api)}")
    print(
        "  por UF do autor (político ligado; None = sem autor): "
        f"{dict(Counter(uf_do_politico.get(x.politico_id) for x in api).most_common(10))}"
    )
    resumo(
        f"linhas da API atribuídas a parlamentares do {UF} (como no relatorio_uf.py)",
        [
            x
            for x in api
            if x.politico_id in ids_uf
            or (
                x.politico_id is None and x.nome_autor and normalizar_nome(x.nome_autor) in nomes_uf
            )
        ],
    )
    resumo(
        "todas as linhas da API sem autor (politico_id nulo)",
        [x for x in api if x.politico_id is None],
    )
    resumo(
        f"linhas da API com destino em município do {UF}",
        [x for x in api if x.cod_ibge_destino in cods_uf],
    )
engine.dispose()
