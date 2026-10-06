"""Senado Federal: senadores em exercício de uma UF e sua atuação.

Fontes (documentação: https://legis.senado.leg.br/dadosabertos/docs/):
- `/senador/lista/atual.json`: senadores em exercício, partido, UF e mandato.
  O detalhe `/senador/{codigo}` NÃO é consultado: traz data de nascimento e endereço,
  e o arquivo de respostas brutas guarda tudo o que chega (LGPD).
- `/processo?codigoParlamentarAutor=&ano=`: matérias com o senador entre os autores
  (substitui `/senador/{codigo}/autorias`, marcado como descontinuado pela fonte).
- `/votacao?codigoParlamentar=&dataInicio=&dataFim=`: votações nominais e o voto do
  senador (substitui `/senador/{codigo}/votacoes`, também descontinuado).
- `/senador/{codigo}/comissoes.json`: comissões de que é ou foi membro.
"""

import re
from datetime import date

import httpx
from sqlalchemy import delete
from sqlalchemy.orm import Session

from rastro.politicos import lgpd
from rastro.politicos.comum import data, get_json_com_origem, gravar, upsert_politico
from rastro.politicos.modelos import SENADOR, PolComissao, PolProposicao, PolVotacao

API = "https://legis.senado.leg.br/dadosabertos"

# "RQS 36/2025" -> ("RQS", "36", 2025)
_IDENT = re.compile(r"^(\S+) (\S+)/(\d{4})$")


def _lista(valor) -> list:
    """O JSON do Senado (convertido de XML) traz um objeto em vez de lista quando há 1 item."""
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def _url(caminho: str, params: dict | None = None) -> str:
    return str(httpx.URL(f"{API}{caminho}", params=params))


def coletar_senadores(session: Session, client: httpx.Client, uf: str) -> dict[str, int]:
    """Grava os senadores em exercício da UF. Devolve {código no Senado: pol_politico.id}."""
    url = _url("/senador/lista/atual.json")
    dados, rid = get_json_com_origem(client, url, redator=lgpd.SENADO_LISTA)
    mapa = {}
    for p in _lista(dados["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]):
        ident, mandato = p["IdentificacaoParlamentar"], p.get("Mandato", {})
        if ident.get("UfParlamentar") != uf:
            continue
        primeira = mandato.get("PrimeiraLegislaturaDoMandato", {})
        segunda = mandato.get("SegundaLegislaturaDoMandato", {})
        codigo = ident["CodigoParlamentar"]
        mapa[codigo] = upsert_politico(
            session,
            {
                "fonte": "senado",
                "id_fonte": codigo,
                "cargo": SENADOR,
                "nome": ident["NomeParlamentar"],
                "partido": ident.get("SiglaPartidoParlamentar"),
                "uf": uf,
                "situacao": mandato.get("DescricaoParticipacao"),
                "em_exercicio": True,
                "mandato_inicio": data(primeira.get("DataInicio")),
                "mandato_fim": data(segunda.get("DataFim") or primeira.get("DataFim")),
                "url_fonte": url,
                "url_pagina": ident.get("UrlPaginaParlamentar"),
                "resposta_id": rid,
            },
        )
    session.commit()
    return mapa


def coletar_materias(
    session: Session, client: httpx.Client, codigo: str, politico_id: int, ano: int
) -> int:
    url = _url("/processo", {"codigoParlamentarAutor": codigo, "ano": ano})
    itens, rid = get_json_com_origem(client, url)
    linhas = []
    for m in itens:
        ident = _IDENT.match(m.get("identificacao") or "")
        linhas.append(
            {
                "politico_id": politico_id,
                "id_fonte": str(m["id"]),
                "sigla_tipo": ident[1] if ident else None,
                "numero": ident[2] if ident else None,
                "ano": int(ident[3]) if ident else ano,
                "ementa": m.get("ementa"),
                "data_apresentacao": data(m.get("dataApresentacao")),
                "autoria": m.get("autoria"),
                "url_fonte": url,
                "url_pagina": m.get("urlDocumento"),
                "resposta_id": rid,
            }
        )
    n = gravar(session, PolProposicao, linhas, ["politico_id", "id_fonte"]) if linhas else 0
    session.commit()
    return n


def coletar_votacoes(
    session: Session, client: httpx.Client, codigo: str, politico_id: int, ano: int
) -> int:
    fim = min(date(ano, 12, 31), date.today())
    url = _url(
        "/votacao",
        {"codigoParlamentar": codigo, "dataInicio": f"{ano}-01-01", "dataFim": fim.isoformat()},
    )
    itens, rid = get_json_com_origem(client, url)
    linhas = []
    for v in itens:
        voto = next((x for x in v.get("votos", []) if str(x["codigoParlamentar"]) == codigo), None)
        if voto is None:
            continue
        linhas.append(
            {
                "politico_id": politico_id,
                "id_votacao": str(v["codigoSessaoVotacao"]),
                "data": data(v["dataSessao"]),
                "voto": voto["siglaVotoParlamentar"],
                "voto_descricao": voto.get("descricaoVotoParlamentar"),
                "orgao": (v.get("informeLegislativo") or {}).get("siglaColegiado"),
                "materia": v.get("identificacao"),
                "descricao": v.get("descricaoVotacao"),
                "url_fonte": url,
                "resposta_id": rid,
            }
        )
    n = gravar(session, PolVotacao, linhas, ["politico_id", "id_votacao"]) if linhas else 0
    session.commit()
    return n


def coletar_comissoes(session: Session, client: httpx.Client, codigo: str, politico_id: int) -> int:
    url = _url(f"/senador/{codigo}/comissoes.json")
    dados, rid = get_json_com_origem(client, url)
    parlamentar = dados["MembroComissaoParlamentar"]["Parlamentar"]
    comissoes = _lista((parlamentar.get("MembroComissoes") or {}).get("Comissao"))
    session.execute(delete(PolComissao).where(PolComissao.politico_id == politico_id))
    for c in comissoes:
        ident = c["IdentificacaoComissao"]
        session.add(
            PolComissao(
                politico_id=politico_id,
                codigo=ident["CodigoComissao"],
                sigla=ident["SiglaComissao"],
                nome=ident["NomeComissao"],
                casa=ident.get("SiglaCasaComissao"),
                participacao=c.get("DescricaoParticipacao"),
                data_inicio=data(c.get("DataInicio")),
                data_fim=data(c.get("DataFim")),
                url_fonte=url,
                resposta_id=rid,
            )
        )
    session.commit()
    return len(comissoes)
