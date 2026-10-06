"""TSE: eleitos de 2024 (prefeitos e vereadores) e 2022 (governador e deputados estaduais).

Fontes (Portal de Dados Abertos do TSE, https://dadosabertos.tse.jus.br):
- "Candidatos" `consulta_cand_{ano}.zip`: um CSV por UF (`consulta_cand_{ano}_{UF}.csv`,
  `;`, Latin-1) com 50 colunas, entre elas CPF, data de nascimento, título de eleitor e
  e-mail. O arquivo bruto guarda só o CSV da UF, sem as colunas pessoais (`COLUNAS_PESSOAIS`),
  com o SHA-256 do ZIP original (conferência: baixar de novo a URL e comparar).
- "Códigos oficiais de UF e municípios segundo o TSE e o IBGE" `municipio_tse_ibge.zip`:
  correspondência oficial código TSE (`SG_UE`) <-> código IBGE. A coleta exige par único
  para todos os municípios da UF; se não houver, falha sem gravar.

Regra de eleitos, por município (ou UF) e cargo: entre as eleições do ano no arquivo
(ordinária e suplementares), vale a mais recente que tem eleitos; dentro dela, os
candidatos com situação de totalização ELEITO, ELEITO POR QP ou ELEITO POR MÉDIA
(no 2º turno, a linha do 2º turno). Sem eleitos, o cargo fica como pendência, com o motivo.

Senador e deputados federais vêm da Câmara e do Senado (quem está em exercício); vice-
prefeito, vice-governador e suplentes de senador estão fora do escopo.
"""

import csv
import io
import zipfile
from collections import defaultdict
from datetime import datetime

import httpx
from sqlalchemy import delete
from sqlalchemy.orm import Session

from rastro.coletores.arquivo import com_redacao, resposta_id
from rastro.coletores.redacao import redator_csv
from rastro.politicos.comum import upsert_politico
from rastro.politicos.modelos import (
    DEPUTADO_ESTADUAL,
    DEPUTADO_FEDERAL,
    GOVERNADOR,
    PREFEITO,
    SENADOR,
    VEREADOR,
    PolPendencia,
    PolPolitico,
)

URL_CANDIDATOS = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_{ano}.zip"
)
URL_MUNICIPIOS = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/municipio_tse_ibge/municipio_tse_ibge.zip"
)

# Colunas de dados pessoais: não vão para o arquivo bruto nem para as tabelas (LGPD).
COLUNAS_PESSOAIS = (
    "NM_CANDIDATO",
    "NM_SOCIAL_CANDIDATO",
    "NR_CPF_CANDIDATO",
    "DS_EMAIL",
    "SG_UF_NASCIMENTO",
    "DT_NASCIMENTO",
    "NR_TITULO_ELEITORAL_CANDIDATO",
    "CD_GENERO",
    "DS_GENERO",
    "CD_GRAU_INSTRUCAO",
    "DS_GRAU_INSTRUCAO",
    "CD_ESTADO_CIVIL",
    "DS_ESTADO_CIVIL",
    "CD_COR_RACA",
    "DS_COR_RACA",
    "CD_OCUPACAO",
    "DS_OCUPACAO",
)

ELEITO = {"ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA"}
CARGOS = {
    2024: {"PREFEITO": PREFEITO, "VEREADOR": VEREADOR},
    2022: {"GOVERNADOR": GOVERNADOR, "DEPUTADO ESTADUAL": DEPUTADO_ESTADUAL},
    # 2026: mandatos a partir de 2027; senador e deputados federais também vêm do TSE
    2026: {
        "GOVERNADOR": GOVERNADOR,
        "SENADOR": SENADOR,
        "DEPUTADO FEDERAL": DEPUTADO_FEDERAL,
        "DEPUTADO ESTADUAL": DEPUTADO_ESTADUAL,
    },
}


def redator_candidatos(ano: int, uf: str):
    return redator_csv(
        COLUNAS_PESSOAIS,
        filtro=lambda linha: linha["SG_UF"] == uf,
        descricao_filtro=f"só SG_UF={uf}",
        encoding="latin-1",
        membro_zip=f"consulta_cand_{ano}_{uf}.csv",
    )


def _csv_do_zip(conteudo: bytes, membro: str) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        texto = z.read(membro).decode("latin-1")
    return list(csv.DictReader(io.StringIO(texto), delimiter=";"))


def _baixar(client: httpx.Client, url: str, redator=None) -> httpx.Response:
    resp = client.get(url, extensions=com_redacao(redator), headers={"Accept": "*/*"})
    resp.raise_for_status()
    return resp


class CruzamentoIncompleto(Exception):
    """A tabela TSE <-> IBGE não dá par único para todos os municípios da UF."""


def cruzamento_municipios(client: httpx.Client, uf: str, codigos_ibge: set[int]):
    """{código TSE: código IBGE} da UF, exigindo par único e cobertura total."""
    resp = _baixar(client, URL_MUNICIPIOS)
    linhas = [r for r in _csv_do_zip(resp.content, "municipio_tse_ibge.csv") if r["SG_UF"] == uf]
    tse_ibge: dict[str, set[int]] = defaultdict(set)
    ibge_tse: dict[int, set[str]] = defaultdict(set)
    for r in linhas:
        tse_ibge[r["CD_MUNICIPIO_TSE"]].add(int(r["CD_MUNICIPIO_IBGE"]))
        ibge_tse[int(r["CD_MUNICIPIO_IBGE"])].add(r["CD_MUNICIPIO_TSE"])
    problemas = [f"TSE {k} -> {sorted(v)}" for k, v in tse_ibge.items() if len(v) > 1]
    problemas += [f"IBGE {k} -> {sorted(v)}" for k, v in ibge_tse.items() if len(v) > 1]
    problemas += [f"IBGE {c} sem par" for c in sorted(codigos_ibge - set(ibge_tse))]
    if problemas:
        raise CruzamentoIncompleto("; ".join(problemas[:20]))
    return {k: next(iter(v)) for k, v in tse_ibge.items()}, resposta_id(resp)


def _data(texto: str) -> datetime:
    return datetime.strptime(texto, "%d/%m/%Y")


def selecionar_eleitos(linhas: list[dict], cargos: dict[str, str]):
    """Aplica a regra de eleitos.

    Gera (unidade, cargo, eleitos, eleições suplementares sem resultado, candidatos com
    2º turno pendente). Há 2º turno pendente quando a eleição mais recente tem candidatos
    com situação "2º TURNO" e ainda nenhum eleito no 2º turno; aí não há eleitos.
    """
    grupos: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in linhas:
        if r["DS_CARGO"] in cargos:
            grupos[(r["SG_UE"], r["DS_CARGO"])].append(r)
    for (ue, cargo), rs in sorted(grupos.items()):
        por_eleicao: dict[str, list[dict]] = defaultdict(list)
        for r in rs:
            por_eleicao[r["CD_ELEICAO"]].append(r)
        ordem = sorted(por_eleicao.values(), key=lambda e: _data(e[0]["DT_ELEICAO"]))
        com_eleitos = [e for e in ordem if any(r["DS_SIT_TOT_TURNO"] in ELEITO for r in e)]
        eleitos = []
        if com_eleitos:
            vistos = set()
            for r in com_eleitos[-1]:
                if r["DS_SIT_TOT_TURNO"] in ELEITO and r["SQ_CANDIDATO"] not in vistos:
                    vistos.add(r["SQ_CANDIDATO"])
                    eleitos.append(r)
        ultima = com_eleitos[-1] if com_eleitos else None
        # suplementares sem resultado posteriores à última eleição com eleitos
        posteriores = [
            e
            for e in ordem
            if e[0]["CD_TIPO_ELEICAO"] == "1"
            and e not in com_eleitos
            and (ultima is None or _data(e[0]["DT_ELEICAO"]) > _data(ultima[0]["DT_ELEICAO"]))
        ]
        recente = ordem[-1]
        segundo_turno = sorted(
            {r["NM_URNA_CANDIDATO"] for r in recente if r["DS_SIT_TOT_TURNO"] == "2º TURNO"}
        )
        if segundo_turno and any(
            r["NR_TURNO"] == "2" and r["DS_SIT_TOT_TURNO"] in ELEITO for r in recente
        ):
            segundo_turno = []
        if segundo_turno:
            eleitos = []
        yield ue, cargo, eleitos, posteriores, segundo_turno


def _motivo(cargo_tse: str, posteriores: list[list[dict]]) -> str:
    base = f"Não consta {cargo_tse.lower()} eleito no arquivo do TSE."
    if posteriores:
        e = posteriores[-1][0]
        quando = f"{e['DS_ELEICAO']} marcada para {e['DT_ELEICAO']}"
        return f"{base} {quando}, ainda sem resultado no arquivo."
    return base


def coletar_eleitos(
    session: Session, client: httpx.Client, ano: int, uf: str, codigos_ibge: set[int]
) -> dict:
    """Grava os eleitos do ano. Substitui por inteiro os registros TSE do ano e da UF."""
    cargos = CARGOS[ano]
    municipal = ano == 2024
    tse_ibge, rid_mun = cruzamento_municipios(client, uf, codigos_ibge) if municipal else ({}, None)
    url = URL_CANDIDATOS.format(ano=ano)
    resp = _baixar(client, url, redator_candidatos(ano, uf))
    rid = resposta_id(resp)
    linhas = [
        r for r in _csv_do_zip(resp.content, f"consulta_cand_{ano}_{uf}.csv") if r["SG_UF"] == uf
    ]

    session.execute(
        delete(PolPolitico).where(
            PolPolitico.fonte == "tse", PolPolitico.eleicao_ano == ano, PolPolitico.uf == uf
        )
    )
    session.execute(
        delete(PolPendencia).where(
            PolPendencia.fonte == "tse", PolPendencia.eleicao_ano == ano, PolPendencia.uf == uf
        )
    )
    resumo = {"eleitos": 0, "pendencias": 0, "unidades": set()}
    sem_par = set()
    for ue, cargo_tse, eleitos, posteriores, segundo_turno in selecionar_eleitos(linhas, cargos):
        cargo = cargos[cargo_tse]
        if posteriores:
            # há eleição posterior (suplementar) sem resultado: o eleito anterior não vale
            eleitos = []
        cod_ibge = tse_ibge.get(ue) if municipal else None
        if municipal and cod_ibge is None:
            sem_par.add(ue)
            continue
        resumo["unidades"].add(ue)
        for r in eleitos:
            suplementar = r["CD_TIPO_ELEICAO"] == "1"
            situacao = (
                r["DS_SIT_TOT_TURNO"]
                + (f" ({r['DS_ELEICAO']}, {r['DT_ELEICAO']})" if suplementar else "")
                + (" (2º turno)" if r["NR_TURNO"] == "2" else "")
            )
            upsert_politico(
                session,
                {
                    "fonte": "tse",
                    "id_fonte": r["SQ_CANDIDATO"],
                    "cargo": cargo,
                    "nome": r["NM_URNA_CANDIDATO"],
                    "partido": r["SG_PARTIDO"],
                    "uf": uf,
                    "cod_ibge": cod_ibge,
                    "situacao": situacao,
                    "em_exercicio": None,
                    "eleicao_ano": ano,
                    "situacao_candidatura": r["DS_SITUACAO_CANDIDATURA"] or None,
                    "data_divulgacao": _data(r["DT_GERACAO"]).date(),
                    "url_fonte": url,
                    "url_pagina": None,
                    "resposta_id": rid,
                },
            )
            resumo["eleitos"] += 1
        if not eleitos:
            session.add(
                PolPendencia(
                    fonte="tse",
                    eleicao_ano=ano,
                    cargo=cargo,
                    uf=uf,
                    cod_ibge=cod_ibge,
                    tipo="segundo_turno" if segundo_turno else "sem_eleito",
                    motivo=(
                        f"2º turno pendente no arquivo do TSE: {', '.join(segundo_turno)}."
                        if segundo_turno
                        else _motivo(cargo_tse, posteriores)
                    ),
                    url_fonte=url,
                    resposta_id=rid,
                )
            )
            resumo["pendencias"] += 1
    if sem_par:
        raise CruzamentoIncompleto(f"códigos TSE sem par IBGE: {sorted(sem_par)}")
    session.commit()
    resumo["unidades"] = len(resumo["unidades"])
    resumo["resposta_municipios"] = rid_mun
    return resumo
