"""Municípios da API de Localidades do IBGE.

Documentação: https://servicodados.ibge.gov.br/api/docs/localidades
"""

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from rastro.coletores.base import get_json_com_origem
from rastro.models import Municipio

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
