"""Municípios da API de Localidades do IBGE.

Documentação: https://servicodados.ibge.gov.br/api/docs/localidades
"""

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from rastro.coletores.base import get_json_com_origem
from rastro.models import Municipio, PopulacaoIbge

URL_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"


def _nome(obj: dict | None) -> str | None:
    return obj["nome"] if obj else None


def normalizar(m: dict) -> dict:
    micro = m.get("microrregiao")
    meso = micro.get("mesorregiao") if micro else None
    imediata = m.get("regiao-imediata")
    intermediaria = imediata.get("regiao-intermediaria") if imediata else None
    # A UF vem aninhada na hierarquia nova ou na antiga; a nova existe para todos os municípios.
    uf = (intermediaria or meso)["UF"]
    return {
        "cod_ibge": m["id"],
        "nome": m["nome"],
        "uf": uf["sigla"],
        "regiao": uf["regiao"]["sigla"],
        "microrregiao": _nome(micro),
        "mesorregiao": _nome(meso),
        "regiao_imediata": _nome(imediata),
        "regiao_intermediaria": _nome(intermediaria),
    }


def coletar(session: Session, client: httpx.Client) -> int:
    dados, origem = get_json_com_origem(client, URL_MUNICIPIOS)
    linhas = [{**normalizar(m), "resposta_id": origem} for m in dados]
    if not linhas:
        return 0
    stmt = insert(Municipio).values(linhas)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Municipio.cod_ibge],
        set_={c: stmt.excluded[c] for c in linhas[0] if c != "cod_ibge"},
    )
    session.execute(stmt)
    session.commit()
    return len(linhas)


# População de todos os municípios (documentação: https://servicodados.ibge.gov.br/api/docs/agregados):
# - estimativas anuais (SIDRA, tabela 6579, variável 9324), os 3 últimos anos publicados;
# - Censo 2022 (SIDRA, tabela 4709, variável 93): a tabela 6579 não tem 2022 nem 2023, e o
#   per capita de 2023 usa a população oficial mais recente até aquele ano (metodologia v1.1).
TABELA_POPULACAO = 6579
URL_POPULACAO = (
    f"https://servicodados.ibge.gov.br/api/v3/agregados/{TABELA_POPULACAO}"
    "/periodos/-3/variaveis/9324?localidades=N6[all]"
)
TABELA_CENSO_2022 = 4709
URL_CENSO_2022 = (
    f"https://servicodados.ibge.gov.br/api/v3/agregados/{TABELA_CENSO_2022}"
    "/periodos/2022/variaveis/93?localidades=N6[all]"
)
# linhas por INSERT (5 parâmetros cada: bem abaixo do limite de 65.535 do PostgreSQL)
LOTE_POPULACAO = 5000
FONTE_POPULACAO = {
    TABELA_POPULACAO: "IBGE, Estimativas de População (SIDRA, tabela 6579)",
    TABELA_CENSO_2022: "IBGE, Censo Demográfico 2022 (SIDRA, tabela 4709)",
}


def normalizar_populacao(dados: list[dict]) -> list[dict]:
    """[{cod_ibge, ano, populacao}] a partir da resposta da API de agregados."""
    linhas = []
    for resultado in dados[0]["resultados"]:
        for s in resultado["series"]:
            for ano, valor in s["serie"].items():
                # o IBGE usa "-", "..." etc. para valor inexistente: fica de fora
                if valor and valor.isdigit():
                    linhas.append(
                        {
                            "cod_ibge": int(s["localidade"]["id"]),
                            "ano": int(ano),
                            "populacao": int(valor),
                        }
                    )
    return linhas


def coletar_populacao(session: Session, client: httpx.Client) -> int:
    total = 0
    for tabela, url in ((TABELA_POPULACAO, URL_POPULACAO), (TABELA_CENSO_2022, URL_CENSO_2022)):
        dados, origem = get_json_com_origem(client, url)
        linhas = [
            {**linha, "tabela": tabela, "resposta_id": origem}
            for linha in normalizar_populacao(dados)
        ]
        # em lotes: o PostgreSQL aceita até 65.535 parâmetros por comando, e 3 anos de
        # estimativas dos 5.570 municípios passam disso
        for i in range(0, len(linhas), LOTE_POPULACAO):
            stmt = insert(PopulacaoIbge).values(linhas[i : i + LOTE_POPULACAO])
            stmt = stmt.on_conflict_do_update(
                index_elements=[PopulacaoIbge.cod_ibge, PopulacaoIbge.ano],
                set_={c: stmt.excluded[c] for c in ("populacao", "tabela", "resposta_id")},
            )
            session.execute(stmt)
        # grava cada tabela antes de baixar a próxima: sem transação aberta durante a
        # consulta à rede (idle_in_transaction_session_timeout em produção)
        session.commit()
        total += len(linhas)
    return total
