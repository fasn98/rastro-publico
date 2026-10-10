"""Câmara dos Deputados: deputados federais de uma UF e sua atuação.

Fontes (documentação: https://dadosabertos.camara.leg.br/swagger/api.html):
- API v2 `/deputados?siglaUf=&idLegislatura=`: quem exerceu mandato na legislatura.
  O detalhe `/deputados/{id}` NÃO é consultado: ele traz CPF e data de nascimento, e o
  arquivo de respostas brutas guarda tudo o que chega (LGPD).
- API v2 `/proposicoes?idDeputadoAutor=&ano=`: proposições com o deputado entre os autores.
- Arquivos anuais `votacoesVotos-AAAA.csv` e `votacoes-AAAA.csv`: votos nominais.
- Arquivo anual `eventosPresencaDeputados-AAAA.csv`: presenças registradas em eventos.
"""

import csv
import io
import logging
import zipfile
from collections.abc import Iterable
from decimal import Decimal

import httpx
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from rastro.coletores.arquivo import com_redacao, resposta_id
from rastro.politicos import lgpd
from rastro.politicos.comum import (
    baixar_csv,
    data,
    data_hora,
    get_json_com_origem,
    gravar,
    gravar_em_lotes,
    upsert_politico,
)
from rastro.politicos.modelos import (
    DEPUTADO_FEDERAL,
    PolDespesaCota,
    PolEventoMandato,
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


def _params_proposicoes(id_camara: int, ano: int) -> dict:
    return {
        "idDeputadoAutor": id_camara,
        "ano": ano,
        "itens": 100,
        "ordem": "ASC",
        "ordenarPor": "id",
    }


def url_proposicoes(id_camara: int, ano: int) -> str:
    """Endereço da 1ª página das proposições, como fica no arquivo de respostas brutas."""
    return str(httpx.URL(f"{API}/proposicoes", params=_params_proposicoes(id_camara, ano)))


def coletar_proposicoes(
    session: Session, client: httpx.Client, id_camara: int, politico_id: int, ano: int
) -> int:
    params = _params_proposicoes(id_camara, ano)
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

    def linhas():
        for v in votos:
            politico_id = mapa.get(int(v["deputado_id"]))
            if politico_id is None:
                continue
            sobre = info.get(v["idVotacao"], {})
            yield {
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

    n = gravar_em_lotes(session, PolVotacao, linhas(), ["politico_id", "id_votacao"])
    session.commit()
    return n


def coletar_presencas(
    session: Session, client: httpx.Client, ano: int, mapa: dict[int, int]
) -> int:
    url = f"{ARQUIVOS}/eventosPresencaDeputados/csv/eventosPresencaDeputados-{ano}.csv"
    presencas, rid, _ = baixar_csv(client, url)
    linhas = (
        {
            "politico_id": mapa[int(p["idDeputado"])],
            "id_evento": p["idEvento"],
            "data_hora_inicio": data_hora(p["dataHoraInicio"]),
            "url_fonte": p["uriEvento"],
            "resposta_id": rid,
        }
        for p in presencas
        if int(p["idDeputado"]) in mapa
    )
    n = gravar_em_lotes(session, PolPresenca, linhas, ["politico_id", "id_evento"])
    session.commit()
    return n


def mapa_gravado(session: Session, uf: str) -> dict[int, int]:
    rows = session.execute(
        select(PolPolitico.id_fonte, PolPolitico.id).where(
            PolPolitico.fonte == "camara", PolPolitico.uf == uf
        )
    )
    return {int(id_fonte): pid for id_fonte, pid in rows}


def coletar_historico(
    session: Session, client: httpx.Client, id_camara: int, politico_id: int
) -> int:
    """Eventos do mandato na legislatura (posse, licença, reassunção, afastamento...).

    A resposta traz o e-mail de gabinete em cada evento: vai ao arquivo bruto sem ele.
    """
    url = f"{API}/deputados/{id_camara}/historico"
    dados, rid = get_json_com_origem(client, url, redator=lgpd.CAMARA_DEPUTADOS)
    eventos = [
        {
            "politico_id": politico_id,
            "data_hora": data_hora(e["dataHora"]),
            "legislatura": e["idLegislatura"],
            "situacao": e.get("situacao"),
            "condicao_eleitoral": e.get("condicaoEleitoral"),
            "descricao_status": e.get("descricaoStatus"),
            "partido": e.get("siglaPartido"),
            "url_fonte": url,
            "resposta_id": rid,
        }
        for e in dados["dados"]
        if e["idLegislatura"] == LEGISLATURA
    ]
    session.execute(delete(PolEventoMandato).where(PolEventoMandato.politico_id == politico_id))
    if eventos:
        session.execute(insert(PolEventoMandato), eventos)
    session.commit()
    return len(eventos)


URL_COTA = "https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"


def coletar_cota(
    session: Session, client: httpx.Client, ano: int, ufs: str | Iterable[str], mapa: dict[int, int]
) -> int:
    """Despesas da cota parlamentar do ano dos deputados em `mapa` (substitui o ano).

    O arquivo é nacional: várias UFs saem de um download só.
    """
    siglas = {ufs} if isinstance(ufs, str) else set(ufs)
    url = URL_COTA.format(ano=ano)
    resp = client.get(
        url, extensions=com_redacao(lgpd.cota(ano, siglas)), headers={"Accept": "*/*"}
    )
    resp.raise_for_status()
    rid = resposta_id(resp)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        texto = z.read(f"Ano-{ano}.csv").decode("utf-8-sig")
    session.execute(
        delete(PolDespesaCota).where(
            PolDespesaCota.ano == ano, PolDespesaCota.politico_id.in_(set(mapa.values()))
        )
    )
    # gravação em lotes: com todas as UFs, o ano inteiro não cabe numa lista
    linhas, total = [], 0
    for n, r in enumerate(csv.DictReader(io.StringIO(texto), delimiter=";"), start=1):
        if r["sgUF"] not in siglas or not r["ideCadastro"]:
            continue
        politico_id = mapa.get(int(r["ideCadastro"]))
        if politico_id is None:
            continue
        doc = lgpd.digitos(r["txtCNPJCPF"])
        pf = len(doc) == 11
        linhas.append(
            {
                "politico_id": politico_id,
                "ano": int(r["numAno"]),
                "mes": int(r["numMes"]),
                "linha": n,
                "categoria": r["txtDescricao"],
                "especificacao": r["txtDescricaoEspecificacao"] or None,
                "fornecedor": None if pf else (lgpd.sem_cpf(r["txtFornecedor"]) or None),
                "cnpj": doc if len(doc) == 14 else None,
                "pessoa_fisica": pf,
                "numero_documento": r["txtNumero"] or None,
                "tipo_documento": r["indTipoDocumento"] or None,
                "data_emissao": data(r["datEmissao"]),
                "valor_documento": _dec(r["vlrDocumento"]),
                "valor_glosa": _dec(r["vlrGlosa"]),
                "valor_liquido": _dec(r["vlrLiquido"]),
                "valor_restituicao": _dec(r["vlrRestituicao"]),
                "ide_documento": r["ideDocumento"] or None,
                "url_documento": r["urlDocumento"] or None,
                "url_fonte": url,
                "resposta_id": rid,
            }
        )
        if len(linhas) >= 2000:
            session.execute(insert(PolDespesaCota), linhas)
            total, linhas = total + len(linhas), []
    if linhas:
        session.execute(insert(PolDespesaCota), linhas)
    session.commit()
    return total + len(linhas)


def _dec(texto: str | None) -> Decimal | None:
    return Decimal(texto) if texto not in (None, "") else None
