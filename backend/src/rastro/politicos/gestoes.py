"""Prefeitos eleitos em cada exercício, como registrados pelo TSE (ADR-0018).

Fonte: `consulta_cand_{ano}.zip` do TSE (o mesmo arquivo dos eleitos, com a mesma redação
LGPD), cargos PREFEITO (11) e VICE-PREFEITO (12). O arquivo da eleição ordinária traz
também as suplementares do mesmo mandato: o de 2020 cobre o mandato 2021–2024 e o de 2024,
o mandato 2025–2028.

O TSE registra quem foi **eleito**, não quem exerceu o cargo (morte, renúncia, afastamento
e interinidade não aparecem). Na cassação, o TSE reescreve o resultado original: a eleição
ordinária fica sem eleito e o vencedor original não aparece como eleito. Por isso:

- vale, em cada mandato, a eleição mais recente com eleito;
- se ela for suplementar (data D), os exercícios anteriores ao ano de D ficam "sem eleito
  válido no arquivo atual do TSE", e o ano de D e os seguintes dizem que a suplementar de D
  elegeu a chapa; o eleito original cassado não é nomeado e o motivo não é citado;
- o vice aparece ao lado do titular; nada é inferido sobre quem exerceu o cargo;
- a mesma pessoa não é ligada entre mandatos (o nome de urna muda e o CPF não é guardado).

Partido = o da eleição, como no TSE, só como texto ao lado do nome.
"""

from collections import defaultdict

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from rastro.coletores.arquivo import resposta_id
from rastro.politicos import tse
from rastro.politicos.modelos import PolEleicaoPrefeito

# ano da eleição ordinária -> (início, fim) do mandato
MANDATOS = {2020: (2021, 2024), 2024: (2025, 2028)}
CARGO_PREFEITO, CARGO_VICE = "11", "12"
SEM_ELEITO = "sem eleito válido no arquivo atual do TSE"


class ColetaInvalida(Exception):
    """O arquivo não fecha (município sem par IBGE, prefeito sem vice etc.): nada é gravado."""


def coletar(
    session: Session, client: httpx.Client, ano: int, uf: str, codigos_ibge: set[int]
) -> dict:
    """Grava as eleições de prefeito do arquivo do ano. Substitui por inteiro as da UF."""
    inicio, fim = MANDATOS[ano]
    tse_ibge, _ = tse.cruzamento_municipios(client, uf, codigos_ibge)
    url = tse.URL_CANDIDATOS.format(ano=ano)
    resp = tse._baixar(client, url, tse.redator_candidatos(ano, uf))
    rid = resposta_id(resp)
    grupos: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in tse._csv_do_zip(resp.content, f"consulta_cand_{ano}_{uf}.csv"):
        if r["SG_UF"] == uf and r["CD_CARGO"] in (CARGO_PREFEITO, CARGO_VICE):
            grupos[(r["SG_UE"], r["CD_ELEICAO"])].append(r)

    registros, problemas = [], []
    for (ue, cd_eleicao), linhas in sorted(grupos.items()):
        cod_ibge = tse_ibge.get(ue)
        if cod_ibge is None:
            problemas.append(f"código TSE {ue} sem par IBGE")
            continue
        eleitos = [r for r in linhas if r["DS_SIT_TOT_TURNO"] in tse.ELEITO]
        prefeitos = [r for r in eleitos if r["CD_CARGO"] == CARGO_PREFEITO]
        vices = [r for r in eleitos if r["CD_CARGO"] == CARGO_VICE]
        # prefeito e vice eleitos formam uma chapa: mesmo número, na mesma eleição e turno
        if (
            len(prefeitos) > 1
            or len(vices) != len(prefeitos)
            or (prefeitos and prefeitos[0]["NR_CANDIDATO"] != vices[0]["NR_CANDIDATO"])
        ):
            problemas.append(
                f"{linhas[0]['NM_UE']} ({ue}), eleição {cd_eleicao}: "
                f"{len(prefeitos)} prefeito(s) e {len(vices)} vice(s) eleitos sem chapa única"
            )
            continue
        r0 = linhas[0]
        p, v = (prefeitos[0], vices[0]) if prefeitos else (None, None)
        registros.append(
            {
                "uf": uf,
                "cod_ibge": cod_ibge,
                "eleicao_ano": ano,
                "mandato_inicio": inicio,
                "mandato_fim": fim,
                "cd_eleicao": cd_eleicao,
                "ds_eleicao": r0["DS_ELEICAO"],
                "data_eleicao": tse._data(r0["DT_ELEICAO"]).date(),
                "suplementar": r0["CD_TIPO_ELEICAO"] == "1",
                "turno": int(r0["NR_TURNO"]),
                "prefeito": p and p["NM_URNA_CANDIDATO"].strip(),
                "prefeito_partido": p and p["SG_PARTIDO"],
                "vice": v and v["NM_URNA_CANDIDATO"].strip(),
                "vice_partido": v and v["SG_PARTIDO"],
                "data_divulgacao": tse._data(r0["DT_GERACAO"]).date(),
                "url_fonte": url,
                "resposta_id": rid,
            }
        )
    faltando = codigos_ibge - {r["cod_ibge"] for r in registros}
    if faltando:
        problemas.append(f"municípios sem eleição de prefeito no arquivo: {sorted(faltando)[:20]}")
    if problemas:
        raise ColetaInvalida("; ".join(problemas[:20]))

    session.execute(
        delete(PolEleicaoPrefeito).where(
            PolEleicaoPrefeito.uf == uf, PolEleicaoPrefeito.eleicao_ano == ano
        )
    )
    session.add_all(PolEleicaoPrefeito(**r) for r in registros)
    session.commit()
    return {
        "eleicoes": len(registros),
        "com_eleito": sum(1 for r in registros if r["prefeito"]),
        "municipios": len({r["cod_ibge"] for r in registros}),
    }


# --------------------------------------------------------------------------- regra


def _nome(nome: str, partido: str) -> str:
    return f"{nome} ({partido})"


def chapa(e: PolEleicaoPrefeito) -> str:
    """ "NOME (PARTIDO), vice NOME (PARTIDO)", como no arquivo do TSE."""
    return f"{_nome(e.prefeito, e.prefeito_partido)}, vice {_nome(e.vice, e.vice_partido)}"


def mandatos(eleicoes: list[PolEleicaoPrefeito]) -> list[dict]:
    """Um item por mandato com eleições no banco, em ordem: a eleição que vale e a situação.

    situacao: "ordinaria" (eleito na ordinária, vale o mandato inteiro), "suplementar"
    (eleito só em suplementar) ou "sem_eleito" (nenhuma eleição do mandato tem eleito).
    """
    por_mandato: dict[tuple[int, int], list[PolEleicaoPrefeito]] = defaultdict(list)
    for e in eleicoes:
        por_mandato[(e.mandato_inicio, e.mandato_fim)].append(e)
    saida = []
    for (inicio, fim), es in sorted(por_mandato.items()):
        com_eleito = sorted((e for e in es if e.prefeito), key=lambda e: e.data_eleicao)
        valida = com_eleito[-1] if com_eleito else None
        if valida is None:
            situacao = "sem_eleito"
        else:
            situacao = "suplementar" if valida.suplementar else "ordinaria"
        saida.append({"inicio": inicio, "fim": fim, "situacao": situacao, "eleicao": valida})
    return saida


def texto_do_exercicio(mandato: dict, ano: int) -> str:
    """Quem foi eleito(a) para o mandato, no exercício `ano` (texto aprovado no ADR-0018)."""
    e = mandato["eleicao"]
    if mandato["situacao"] == "ordinaria":
        return chapa(e)
    if mandato["situacao"] == "sem_eleito" or ano < e.data_eleicao.year:
        return SEM_ELEITO
    return f"{SEM_ELEITO}; a eleição suplementar de {e.data_eleicao:%d/%m/%Y} elegeu {chapa(e)}"


def por_exercicio(lista_mandatos: list[dict], anos: list[int]) -> list[dict] | None:
    """[{ano, mandato, texto}] para cada ano; None se algum ano não tem mandato no banco."""
    saida = []
    for ano in anos:
        m = next((m for m in lista_mandatos if m["inicio"] <= ano <= m["fim"]), None)
        if m is None:
            return None
        saida.append(
            {
                "ano": ano,
                "mandato": f"{m['inicio']}–{m['fim']}",
                "texto": texto_do_exercicio(m, ano),
            }
        )
    return saida


def resumo_do_periodo(lista_mandatos: list[dict], anos: list[int]) -> str | None:
    """Texto da coluna "Prefeitos eleitos no período da nota".

    Anos seguidos só se juntam dentro do mesmo mandato, quando o texto é igual:
    "2023–2024: NOME (P), vice NOME (P); 2025: NOME (P), vice NOME (P)".
    """
    itens = por_exercicio(lista_mandatos, anos)
    if itens is None:
        return None
    blocos: list[list] = []
    for i in itens:
        if blocos and blocos[-1][2] == (i["mandato"], i["texto"]):
            blocos[-1][1] = i["ano"]
        else:
            blocos.append([i["ano"], i["ano"], (i["mandato"], i["texto"])])
    return "; ".join(f"{a}{'–' + str(b) if b != a else ''}: {texto}" for a, b, (_, texto) in blocos)


def eleicoes_do_municipio(session: Session, cod_ibge: int) -> list[PolEleicaoPrefeito]:
    return list(
        session.scalars(
            select(PolEleicaoPrefeito)
            .where(PolEleicaoPrefeito.cod_ibge == cod_ibge)
            .order_by(PolEleicaoPrefeito.data_eleicao, PolEleicaoPrefeito.cd_eleicao)
        )
    )


def eleicoes_da_uf(session: Session, uf: str) -> dict[int, list[PolEleicaoPrefeito]]:
    por_municipio: dict[int, list[PolEleicaoPrefeito]] = defaultdict(list)
    for e in session.scalars(
        select(PolEleicaoPrefeito)
        .where(PolEleicaoPrefeito.uf == uf)
        .order_by(PolEleicaoPrefeito.data_eleicao, PolEleicaoPrefeito.cd_eleicao)
    ):
        por_municipio[e.cod_ibge].append(e)
    return por_municipio
