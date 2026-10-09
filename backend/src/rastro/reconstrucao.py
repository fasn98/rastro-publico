"""Reconstrução de linhas do RREO/RGF a partir do arquivo bruto, sem chamar a API.

`conta_demonstrativo` guarda só o que o mapeamento pede; o arquivo bruto guarda tudo.
Daqui sai qualquer linha de qualquer demonstrativo coletado, com o `resposta_id` de
origem, para inspecionar (`rastro reconstruir`) ou gravar (`--gravar`), e para alinhar a
tabela a um mapeamento novo (`rastro aplicar-mapeamento`).
"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from rastro import mapeamento as mp
from rastro.coletores.arquivo import ler_payload
from rastro.models import (
    ContaDemonstrativo,
    DemonstrativoResposta,
    DemonstrativoSiconfi,
    Estado,
    PayloadBruto,
    RespostaBruta,
)

CAMPOS = ("anexo", "rotulo", "cod_conta", "conta", "coluna")


@dataclass
class Filtro:
    anexo: str | None = None
    cod_conta: list[str] | None = None
    coluna: list[str] | None = None
    conta: list[str] | None = None
    cod_ibge: list[int] | None = None
    exercicio: list[int] | None = None
    demonstrativo_id: list[int] | None = None
    # prefixo do tipo de relatório: "RGF" pega RGF e RGF Simplificado
    tipo: str | None = None

    def aceita(self, item: dict) -> bool:
        return (
            (self.anexo is None or item.get("anexo") == self.anexo)
            and (self.cod_conta is None or item.get("cod_conta") in self.cod_conta)
            and (self.coluna is None or item.get("coluna") in self.coluna)
            and (self.conta is None or item.get("conta") in self.conta)
        )


@dataclass
class LinhaReconstruida:
    demonstrativo_id: int
    anexo: str
    rotulo: str
    cod_conta: str
    conta: str
    coluna: str
    valor: Decimal | None
    resposta_id: int

    def chave(self) -> tuple:
        return tuple(getattr(self, c) for c in CAMPOS)


def _demonstrativos(session: Session, f: Filtro):
    q = select(DemonstrativoSiconfi).order_by(DemonstrativoSiconfi.id)
    if f.cod_ibge:
        q = q.where(DemonstrativoSiconfi.cod_ibge.in_(f.cod_ibge))
    if f.exercicio:
        q = q.where(DemonstrativoSiconfi.exercicio.in_(f.exercicio))
    if f.demonstrativo_id:
        q = q.where(DemonstrativoSiconfi.id.in_(f.demonstrativo_id))
    if f.tipo:
        q = q.where(DemonstrativoSiconfi.demonstrativo.startswith(f.tipo))
    return session.scalars(q).all()


def linhas_brutas(session: Session, d: DemonstrativoSiconfi) -> Iterator[tuple[dict, int]]:
    """Todas as linhas do demonstrativo, lidas das respostas brutas (item, resposta_id)."""
    ids = session.scalars(
        select(DemonstrativoResposta.resposta_id)
        .where(DemonstrativoResposta.demonstrativo_id == d.id)
        .order_by(DemonstrativoResposta.resposta_id)
    ).all()
    for rid in ids:
        r = session.get(RespostaBruta, rid)
        dados = json.loads(ler_payload(session.get(PayloadBruto, r.sha256)), parse_float=Decimal)
        for item in dados.get("items", []):
            # a resposta do RGF de um poder traz todas as instituições dele (ex.: Câmara e
            # TCM); cada demonstrativo é de uma instituição só
            if item.get("instituicao") == d.instituicao:
                yield item, rid


def reconstruir(
    session: Session, filtro: Filtro, aceitar: Callable[[dict], bool] | None = None
) -> Iterator[LinhaReconstruida]:
    for d in _demonstrativos(session, filtro):
        for item, rid in linhas_brutas(session, d):
            if filtro.aceita(item) and (aceitar is None or aceitar(item)):
                yield LinhaReconstruida(
                    demonstrativo_id=d.id,
                    anexo=item["anexo"],
                    rotulo=item["rotulo"],
                    cod_conta=item["cod_conta"],
                    conta=item["conta"],
                    coluna=item["coluna"],
                    valor=item.get("valor"),
                    resposta_id=rid,
                )


def _existentes(session: Session, demonstrativo_id: int) -> set[tuple]:
    return {
        tuple(linha)
        for linha in session.execute(
            select(*(getattr(ContaDemonstrativo, c) for c in CAMPOS)).where(
                ContaDemonstrativo.demonstrativo_id == demonstrativo_id
            )
        )
    }


def _atualizar_contagem(session: Session, ids: set[int]) -> None:
    for d in session.scalars(select(DemonstrativoSiconfi).where(DemonstrativoSiconfi.id.in_(ids))):
        d.linhas_gravadas = (
            session.query(ContaDemonstrativo).filter_by(demonstrativo_id=d.id).count()
        )


def gravar(session: Session, linhas: list[LinhaReconstruida]) -> int:
    """Insere as linhas que ainda não estão em conta_demonstrativo. Devolve quantas entraram."""
    novas, vistos = [], {}
    for li in linhas:
        if li.demonstrativo_id not in vistos:
            vistos[li.demonstrativo_id] = _existentes(session, li.demonstrativo_id)
        if li.chave() not in vistos[li.demonstrativo_id]:
            vistos[li.demonstrativo_id].add(li.chave())
            novas.append(li)
    inseridas = 0
    if novas:
        # ON CONFLICT: se outro processo gravou a mesma célula entre a leitura de
        # `_existentes` e este insert, a linha dele vale e esta é ignorada
        ids = session.scalars(
            pg_insert(ContaDemonstrativo)
            .values(
                [
                    {
                        c: getattr(li, c)
                        for c in (*CAMPOS, "valor", "resposta_id", "demonstrativo_id")
                    }
                    for li in novas
                ]
            )
            .on_conflict_do_nothing(constraint="uq_conta_demonstrativo")
            .returning(ContaDemonstrativo.id)
        ).all()
        inseridas = len(ids)
        _atualizar_contagem(session, {li.demonstrativo_id for li in novas})
    session.commit()
    return inseridas


def aplicar_mapeamento(
    session: Session,
    mapeamento: mp.Mapeamento | None = None,
    podar: bool = False,
    tipo: str | None = None,
    se_mudou: bool = False,
) -> dict:
    """Alinha conta_demonstrativo ao mapeamento: reconstrói do bruto o que falta e, com
    `podar`, apaga o que o mapeamento não pede mais (continua no arquivo bruto).

    `tipo` limita a um tipo de relatório ("RGF" = RGF e RGF Simplificado). Com `se_mudou`,
    não faz nada se este mapeamento já foi aplicado a esse tipo (tabela `estado`); serve
    para a coleta aplicar uma versão nova do mapeamento uma vez só.
    """
    mapeamento = mapeamento or mp.padrao()
    chave = f"mapeamento_aplicado:{tipo or 'todos'}"
    marca = session.get(Estado, chave)
    if se_mudou and marca is not None and marca.valor == mapeamento.hash:
        return {"podadas": 0, "reconstruidas": 0, "mapeamento": mapeamento.hash, "pulado": True}
    podadas = reconstruidas = 0
    for d in _demonstrativos(session, Filtro(tipo=tipo)):
        if podar:
            fora = [
                c.id
                for c in session.scalars(
                    select(ContaDemonstrativo).filter_by(demonstrativo_id=d.id)
                )
                if not mapeamento.aceita({k: getattr(c, k) for k in CAMPOS})
            ]
            if fora:
                session.execute(delete(ContaDemonstrativo).where(ContaDemonstrativo.id.in_(fora)))
                podadas += len(fora)
        faltando = list(reconstruir(session, Filtro(demonstrativo_id=[d.id]), mapeamento.aceita))
        reconstruidas += gravar(session, faltando)
        _atualizar_contagem(session, {d.id})
        session.commit()
    session.merge(Estado(chave=chave, valor=mapeamento.hash, atualizado_em=datetime.now(UTC)))
    session.commit()
    return {
        "podadas": podadas,
        "reconstruidas": reconstruidas,
        "mapeamento": mapeamento.hash,
        "pulado": False,
    }
