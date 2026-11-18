"""Situação da coleta de emendas por UF (decisão do Fabio, 17/11/2026, ADR-0024).

A coleta do arquivo em lote do Portal é uma passada só para as UFs de
`RASTRO_POL_EMENDAS_UFS`, gravada numa transação: se falhar, nada é apagado e as linhas da
coleta anterior continuam no banco. Para uma UF já publicada:

- o site continua com os dados anteriores e mostra "Dados de dd/mm/aaaa; a coleta mais
  recente não foi concluída";
- se nenhuma coleta for concluída por mais de 7 dias (`LIMITE_DIAS`) desde a primeira
  falha, a UF ganha um aviso destacado de dados desatualizados, sem sair do site;
- cada falha vai para o log da coleta e para o resumo da execução, com a UF e o motivo (só
  o tipo do erro, ex.: "HTTP 504 após 4 tentativas").

Os dados anteriores só valem se a última coleta com sucesso do arquivo incluiu a UF: cada
coleta com sucesso regrava todas as linhas, e o recorte só traz todas as emendas das UFs
daquela coleta. Se não incluiu, a UF segue a regra de sempre (o portão reprova).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rastro.models import Coleta
from rastro.politicos.modelos import PolColetaUf

FONTE = "pol-emendas"
LIMITE_DIAS = 7


def coleta_vigente(session: Session) -> int | None:
    """Id da última coleta do arquivo concluída com sucesso: as linhas no banco são dela."""
    return session.scalar(
        select(func.max(PolColetaUf.coleta_id)).where(
            PolColetaUf.fonte == FONTE, PolColetaUf.status == "sucesso"
        )
    )


def uf_na_coleta_vigente(session: Session, uf: str) -> bool:
    """A UF estava na última coleta com sucesso do arquivo (todas as linhas dela no banco)."""
    vigente = coleta_vigente(session)
    return vigente is not None and bool(
        session.scalar(
            select(func.count())
            .select_from(PolColetaUf)
            .where(
                PolColetaUf.fonte == FONTE,
                PolColetaUf.uf == uf.upper(),
                PolColetaUf.coleta_id == vigente,
                PolColetaUf.status == "sucesso",
            )
        )
    )


def situacao(session: Session, uf: str, agora: datetime | None = None) -> dict | None:
    """None se a última coleta de emendas da UF terminou com sucesso ou se a UF nunca foi
    coletada. Senão:

    - `dados_de`: fim da última coleta concluída com a UF (None se nunca houve);
    - `falha_desde`: registro da primeira coleta não concluída depois dela;
    - `motivo`: motivo da última coleta não concluída (só o tipo do erro);
    - `dados_anteriores`: os dados da UF no banco são os da última coleta com sucesso;
    - `desatualizada`: mais de `LIMITE_DIAS` dias sem coleta concluída desde `falha_desde`.
    """
    uf = uf.upper()
    agora = agora or datetime.now(UTC)
    linhas = select(PolColetaUf).where(PolColetaUf.fonte == FONTE, PolColetaUf.uf == uf)
    ultima = session.scalar(linhas.order_by(PolColetaUf.id.desc()).limit(1))
    if ultima is None or ultima.status == "sucesso":
        return None
    ok = session.scalar(
        linhas.where(PolColetaUf.status == "sucesso").order_by(PolColetaUf.id.desc()).limit(1)
    )
    primeira_falha = session.scalar(
        linhas.where(PolColetaUf.id > (ok.id if ok else 0)).order_by(PolColetaUf.id).limit(1)
    )
    dados_de = session.get(Coleta, ok.coleta_id).finalizada_em if ok else None
    falha_desde = primeira_falha.registrada_em
    return {
        "dados_de": dados_de.isoformat() if dados_de else None,
        "falha_desde": falha_desde.isoformat(),
        "motivo": ultima.motivo,
        "dados_anteriores": ok is not None and uf_na_coleta_vigente(session, uf),
        "desatualizada": agora - falha_desde > timedelta(days=LIMITE_DIAS),
    }


def falhas_desde(session: Session, desde: datetime | None) -> list[dict]:
    """UFs com coleta de emendas não concluída registrada desde `desde` (início da coleta
    em andamento; sem `desde`, as UFs cuja última coleta não foi concluída)."""
    filtro = [PolColetaUf.fonte == FONTE, PolColetaUf.status != "sucesso"]
    if desde is not None:
        filtro.append(PolColetaUf.registrada_em >= desde)
    ufs = sorted(set(session.scalars(select(PolColetaUf.uf).where(*filtro))))
    saida = []
    for uf in ufs:
        s = situacao(session, uf)
        if s is not None:  # uma coleta posterior pode ter concluído
            saida.append({"uf": uf, **s})
    return saida


def resumo(falhas: list[dict]) -> str:
    """Linha do resumo da execução (`rastro resumo-coleta`)."""
    if not falhas:
        return "Emendas por UF com falha: nenhuma"
    partes = []
    for f in falhas:
        detalhe = f["motivo"] or "falha"
        if f["dados_anteriores"]:
            detalhe += f"; dados de {f['dados_de'][:10]}"
        else:
            detalhe += "; sem dados anteriores válidos"
        detalhe += f"; sem coleta concluída desde {f['falha_desde'][:10]}"
        if f["desatualizada"]:
            detalhe += f"; DESATUALIZADA (mais de {LIMITE_DIAS} dias)"
        partes.append(f"{f['uf']} ({detalhe})")
    return "Emendas por UF com falha: " + "; ".join(partes)
