"""Funções comuns aos coletores do módulo de políticos."""

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date, datetime

import httpx
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from rastro.coletores.arquivo import resposta_id
from rastro.coletores.base import get_json_com_origem
from rastro.politicos.modelos import PolPolitico

__all__ = ["get_json_com_origem", "baixar_csv", "data", "data_hora", "gravar", "upsert_politico"]


def baixar_csv(client: httpx.Client, url: str) -> tuple[list[dict], int | None, str]:
    """Baixa um CSV (`;`, UTF-8 com BOM) inteiro. Devolve (linhas, resposta_id, url)."""
    resp = client.get(url, headers={"Accept": "text/csv"})
    resp.raise_for_status()
    texto = resp.content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(texto), delimiter=";")), resposta_id(resp), url


def data(valor: str | None) -> date | None:
    """'2025-02-05', '2025-02-05T17:34' ou '2025-02-05T17:34:00' -> date."""
    return date.fromisoformat(valor[:10]) if valor else None


def data_hora(valor: str) -> datetime:
    return datetime.fromisoformat(valor)


def gravar(
    session: Session, modelo, linhas: Sequence[dict], chave: Iterable[str], lote=1000
) -> int:
    """Upsert em lotes: atualiza todas as colunas exceto as da chave única."""
    chave = list(chave)
    for i in range(0, len(linhas), lote):
        parte = linhas[i : i + lote]
        stmt = insert(modelo).values(parte)
        stmt = stmt.on_conflict_do_update(
            index_elements=chave,
            set_={c: stmt.excluded[c] for c in parte[0] if c not in chave},
        )
        session.execute(stmt)
    return len(linhas)


def upsert_politico(session: Session, linha: dict) -> int:
    stmt = insert(PolPolitico).values(linha)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_pol_politico",
        set_={
            **{c: stmt.excluded[c] for c in linha if c not in ("fonte", "id_fonte", "cargo")},
            "atualizado_em": func.now(),
        },
    ).returning(PolPolitico.id)
    return session.execute(stmt).scalar_one()
