"""Câmara dos Deputados: deputados federais de uma UF e sua atuação.

Fontes (documentação: https://dadosabertos.camara.leg.br/swagger/api.html):
- API v2 `/deputados?siglaUf=&idLegislatura=`: quem exerceu mandato na legislatura.
  O detalhe `/deputados/{id}` NÃO é consultado: ele traz CPF e data de nascimento, e o
  arquivo de respostas brutas guarda tudo o que chega (LGPD).
- API v2 `/proposicoes?idDeputadoAutor=&ano=`: proposições com o deputado entre os autores.
- Arquivos anuais `votacoesVotos-AAAA.csv` e `votacoes-AAAA.csv`: votos nominais.
- Arquivo anual `eventosPresencaDeputados-AAAA.csv`: presenças registradas em eventos.
"""

import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from rastro.politicos import lgpd
from rastro.politicos.comum import (
    baixar_csv,
    data,
    data_hora,
    get_json_com_origem,
    gravar,
    upsert_politico,
)
from rastro.politicos.modelos import (
    DEPUTADO_FEDERAL,
    PolPolitico,
    PolPresenca,
    PolProposicao,
    PolVotacao,
)

log = logging.getLogger(__name__)

API = "https://dadosabertos.camara.leg.br/api/v2"
ARQUIVOS = "https://dadosabertos.camara.leg.br/arquivos"
LEGISLATURA = 57  # 2023-2027


def paginas(client: httpx.Client, url: str, params: dict, redator=None):
    """Percorre as páginas da API v2 seguindo o link `next`. Gera (itens, resposta_id)."""
    while url:
        dados, rid = get_json_com_origem(client, url, params, redator=redator)
        yield dados["dados"], rid
        url = next((lk["href"] for lk in dados.get("links", []) if lk["rel"] == "next"), None)
        params = None  # o link `next` já traz os parâmetros


def coletar_deputados(
    session: Session, client: httpx.Client, uf: str, legislatura: int = LEGISLATURA
) -> dict[int, int]:
    """Grava os deputados da UF na legislatura. Devolve {id na Câmara: pol_politico.id}.

    A lista da legislatura repete o deputado uma vez por partido pelo qual passou, sem
    indicar qual é o atual. Para quem está em exercício, o partido vem da lista atual;
    para os demais, guardam-se todos os partidos registrados ("PL / PODE"), na ordem da fonte.
    """
    params = {"siglaUf": uf, "itens": 100, "ordem": "ASC", "ordenarPor": "nome"}
    atuais = {
        d["id"]: d
        for itens, _ in paginas(client, f"{API}/deputados", params, lgpd.CAMARA_DEPUTADOS)
        for d in itens
    }
    registros: dict[int, tuple[dict, list[str], int | None]] = {}
    leg = {**params, "idLegislatura": legislatura}
    for itens, rid in paginas(client, f"{API}/deputados", leg, lgpd.CAMARA_DEPUTADOS):
        for d in itens:
            _, partidos, _ = registros.setdefault(d["id"], (d, [], rid))
            if d["siglaPartido"] and d["siglaPartido"] not in partidos:
                partidos.append(d["siglaPartido"])
    mapa = {}
    for id_camara, (d, partidos, rid) in registros.items():
        atual = atuais.get(id_camara)
        mapa[id_camara] = upsert_politico(
            session,
            {
                "fonte": "camara",
                "id_fonte": str(id_camara),
                "cargo": DEPUTADO_FEDERAL,
                "nome": d["nome"],
                "partido": atual["siglaPartido"] if atual else " / ".join(partidos) or None,
                "uf": d["siglaUf"],
                "legislatura": d["idLegislatura"],
                "em_exercicio": atual is not None,
                "url_fonte": d["uri"],
                "url_pagina": f"https://www.camara.leg.br/deputados/{id_camara}",
                "resposta_id": rid,
            },
        )
    session.commit()
    return mapa


def coletar_proposicoes(
    session: Session, client: httpx.Client, id_camara: int, politico_id: int, ano: int
) -> int:
    params = {
        "idDeputadoAutor": id_camara,
        "ano": ano,
        "itens": 100,
        "ordem": "ASC",
        "ordenarPor": "id",
    }
    linhas = []
    for itens, rid in paginas(client, f"{API}/proposicoes", params):
        for p in itens:
            linhas.append(
                {
                    "politico_id": politico_id,
                    "id_fonte": str(p["id"]),
                    "sigla_tipo": p["siglaTipo"],
                    "numero": str(p["numero"]),
                    "ano": p["ano"],
                    "ementa": p["ementa"],
                    "data_apresentacao": data(p.get("dataApresentacao")),
                    "url_fonte": p["uri"],
                    "url_pagina": f"https://www.camara.leg.br/propostas-legislativas/{p['id']}",
                    "resposta_id": rid,
                }
            )
    n = gravar(session, PolProposicao, linhas, ["politico_id", "id_fonte"]) if linhas else 0
    session.commit()
    return n


def coletar_votos(session: Session, client: httpx.Client, ano: int, mapa: dict[int, int]) -> int:
    """Votos nominais do ano dos deputados em `mapa`, a partir dos arquivos anuais."""
    votacoes, _, _ = baixar_csv(client, f"{ARQUIVOS}/votacoes/csv/votacoes-{ano}.csv")
    info = {v["id"]: v for v in votacoes}
    votos, rid, _ = baixar_csv(client, f"{ARQUIVOS}/votacoesVotos/csv/votacoesVotos-{ano}.csv")
    linhas = []
    for v in votos:
        politico_id = mapa.get(int(v["deputado_id"]))
        if politico_id is None:
            continue
        sobre = info.get(v["idVotacao"], {})
        linhas.append(
            {
                "politico_id": politico_id,
                "id_votacao": v["idVotacao"],
                "data": data(sobre.get("data") or v["dataHoraVoto"]),
                "voto": v["voto"],
                "voto_descricao": None,
                "orgao": sobre.get("siglaOrgao") or None,
                "materia": None,
                "descricao": sobre.get("descricao") or None,
                "url_fonte": v["uriVotacao"],
                "resposta_id": rid,
            }
        )
    n = gravar(session, PolVotacao, linhas, ["politico_id", "id_votacao"]) if linhas else 0
    session.commit()
    return n


def coletar_presencas(
    session: Session, client: httpx.Client, ano: int, mapa: dict[int, int]
) -> int:
    url = f"{ARQUIVOS}/eventosPresencaDeputados/csv/eventosPresencaDeputados-{ano}.csv"
    presencas, rid, _ = baixar_csv(client, url)
    linhas = [
        {
            "politico_id": mapa[int(p["idDeputado"])],
            "id_evento": p["idEvento"],
            "data_hora_inicio": data_hora(p["dataHoraInicio"]),
            "url_fonte": p["uriEvento"],
            "resposta_id": rid,
        }
        for p in presencas
        if int(p["idDeputado"]) in mapa
    ]
    n = gravar(session, PolPresenca, linhas, ["politico_id", "id_evento"]) if linhas else 0
    session.commit()
    return n


def mapa_gravado(session: Session, uf: str) -> dict[int, int]:
    rows = session.execute(
        select(PolPolitico.id_fonte, PolPolitico.id).where(
            PolPolitico.fonte == "camara", PolPolitico.uf == uf
        )
    )
    return {int(id_fonte): pid for id_fonte, pid in rows}
