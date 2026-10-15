"""Portão de políticos por UF (aprovado pelo Fabio em 10/10 e 15/10/2026).

Uma UF só tem os políticos publicados se passar neste portão **e** no portão fiscal
(`rastro.portao`). Conferências, só no banco (nenhuma consulta à rede):

1. **Coletas:** a última coleta da UF em cada fonte (`pol_coleta_uf`) terminou com sucesso.
   Câmara, Senado, TSE e emendas do arquivo em lote. Fonte sem coleta da UF: "ainda não
   coletada", para não ser lida como falha.
2. **Eleitos do TSE:** há eleitos da UF em 2022 e 2024 (o DF não tem eleição municipal). O
   cruzamento TSE↔IBGE em 100% já é exigido na coleta: falhou, nada é gravado. Cargo de
   2026 com 2º turno pendente fica oculto pela regra de sempre e não reprova a UF.
3. **Exceções de emendas:** toda exceção aprovada (`excecoes_emendas.toml`) de político da
   UF casou com pelo menos uma linha do arquivo. Emenda sem vínculo por ambiguidade (nome
   repetido, mais de um "Código do Autor") NÃO reprova a UF: a regra já a mostra sem link
   (opção (a), decidida pelo Fabio em 10/10/2026).
4. **Prefeitos eleitos por exercício** (ADR-0018): só com `pol_publicar_gestoes` ligada, a
   última coleta de prefeitos da UF terminou com sucesso (chapa única é exigida na coleta).
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rastro.config import get_settings
from rastro.politicos import tse, vinculo
from rastro.politicos.modelos import PolColetaUf, PolEmenda, PolPolitico

log = logging.getLogger(__name__)

# fonte -> (nome, "ainda não coletados/coletadas", com a concordância do nome)
FONTES = {
    "pol-camara": ("deputados federais (Câmara)", "coletados"),
    "pol-senado": ("senadores (Senado)", "coletados"),
    "pol-tse": ("eleitos (TSE)", "coletados"),
    "pol-emendas": ("emendas", "coletadas"),
}
ELEICOES_OBRIGATORIAS = (2022, 2024)


def _ultima(session: Session, fonte: str, uf: str) -> PolColetaUf | None:
    return session.scalar(
        select(PolColetaUf)
        .where(PolColetaUf.fonte == fonte, PolColetaUf.uf == uf)
        .order_by(PolColetaUf.id.desc())
        .limit(1)
    )


def _coletas(session: Session, uf: str, fontes: dict[str, tuple[str, str]]) -> list[str]:
    motivos = []
    for fonte, (nome, coletados) in fontes.items():
        ultima = _ultima(session, fonte, uf)
        if ultima is None:
            motivos.append(f"{nome} da UF ainda não {coletados}")
        elif ultima.status != "sucesso":
            motivos.append(
                f"{nome}: última coleta terminou {ultima.status}"
                + (f" ({ultima.motivo})" if ultima.motivo else "")
            )
    return motivos


def _eleitos(session: Session, uf: str) -> list[str]:
    motivos = []
    for ano in ELEICOES_OBRIGATORIAS:
        if ano in tse.ELEICOES_MUNICIPAIS and uf in tse.UFS_SEM_ELEICAO_MUNICIPAL:
            continue
        n = session.scalar(
            select(func.count())
            .select_from(PolPolitico)
            .where(PolPolitico.fonte == "tse", PolPolitico.eleicao_ano == ano, PolPolitico.uf == uf)
        )
        if not n:
            motivos.append(f"nenhum eleito do TSE de {ano} gravado para a UF")
    return motivos


def _excecoes(session: Session, uf: str) -> list[str]:
    motivos = []
    for e in vinculo.carregar_excecoes():
        p = session.scalar(
            select(PolPolitico).where(
                PolPolitico.fonte == "camara", PolPolitico.id_fonte == str(e["camara_id"])
            )
        )
        if p is None or p.uf != uf:
            continue  # o político da exceção é de outra UF (ou ainda não foi coletado)
        n = session.scalar(
            select(func.count())
            .select_from(PolEmenda)
            .where(
                PolEmenda.politico_id == p.id,
                PolEmenda.vinculo == "excecao",
                PolEmenda.nome_autor == e["texto_fonte"],
            )
        )
        if not n:
            motivos.append(f"exceção aprovada de emenda sem linha no arquivo: {e['texto_fonte']}")
    return motivos


def avaliar_uf(session: Session, uf: str) -> dict:
    """{"aprovada": bool, "motivos": [...]} dos políticos da UF."""
    uf = uf.upper()
    motivos = _coletas(session, uf, FONTES)
    motivos += _eleitos(session, uf)
    motivos += _excecoes(session, uf)
    if get_settings().pol_publicar_gestoes and uf not in tse.UFS_SEM_ELEICAO_MUNICIPAL:
        motivos += _coletas(
            session, uf, {"pol-tse-prefeitos": ("prefeitos eleitos (TSE)", "coletados")}
        )
    return {"aprovada": not motivos, "motivos": motivos}


def avaliar_uf_isolado(session: Session, uf: str) -> dict:
    """Como `avaliar_uf`, mas um erro aqui nunca derruba o portão fiscal: vira reprovação."""
    try:
        r = avaliar_uf(session, uf)
    except Exception as exc:
        session.rollback()
        r = {
            "aprovada": False,
            "motivos": [f"avaliação não pôde ser feita ({type(exc).__name__}: {exc})"],
        }
    log.info(
        "Portão políticos %s: %s%s",
        uf,
        "aprovada" if r["aprovada"] else "reprovada",
        "" if r["aprovada"] else f" ({'; '.join(r['motivos'])})",
    )
    return r
