"""Entes da Federação do SICONFI (API de Dados Abertos do Tesouro Nacional).

Documentação: https://apidatalake.tesouro.gov.br/docs/siconfi/
"""

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from rastro.coletores.base import get_json
from rastro.models import EnteSiconfi

URL_ENTES = "https://apidatalake.tesouro.gov.br/ords/cdwhprd/siconfi/tt/entes"

# Códigos IBGE das UFs. Necessário porque o SICONFI devolve uf="BR" para estados e DF.
UF_POR_CODIGO = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA",
    31: "MG", 32: "ES", 33: "RJ", 35: "SP",
    41: "PR", 42: "SC", 43: "RS",
    50: "MS", 51: "MT", 52: "GO", 53: "DF",
}  # fmt: skip


def paginas(
    client: httpx.Client, url: str, params: dict | None = None, limite: int = 5000, **kwargs
):
    """Percorre a paginação do ORDS (Oracle REST Data Services) usando offset/hasMore."""
    offset = 0
    while True:
        dados = get_json(
            client, url, params={**(params or {}), "offset": offset, "limit": limite}, **kwargs
        )
        itens = dados.get("items", [])
        yield from itens
        if not dados.get("hasMore") or not itens:
            break
        offset += len(itens)


def normalizar(e: dict) -> dict:
    esfera = e["esfera"]
    if esfera in ("E", "D"):
        uf = UF_POR_CODIGO[e["cod_ibge"]]
    elif esfera == "U":
        uf = None
    else:
        uf = e["uf"]
    return {
        "cod_ibge": e["cod_ibge"],
        "nome": e["ente"],
        "esfera": esfera,
        "uf": uf,
        "regiao": e["regiao"],
        # vem como texto com espaços: "1  " ou "0  "
        "capital": str(e.get("capital", "")).strip() == "1",
        "populacao": e.get("populacao"),
        "cnpj": e.get("cnpj"),
        "exercicio": e["exercicio"],
    }


def coletar(session: Session, client: httpx.Client) -> int:
    linhas = [normalizar(e) for e in paginas(client, URL_ENTES)]
    if not linhas:
        return 0
    stmt = insert(EnteSiconfi).values(linhas)
    stmt = stmt.on_conflict_do_update(
        index_elements=[EnteSiconfi.cod_ibge],
        set_={c: stmt.excluded[c] for c in linhas[0] if c != "cod_ibge"},
    )
    session.execute(stmt)
    session.commit()
    return len(linhas)
