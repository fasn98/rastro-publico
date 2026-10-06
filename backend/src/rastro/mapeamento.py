"""Mapeamento das linhas/colunas do RREO/RGF guardadas em `conta_demonstrativo`.

O arquivo bruto guarda tudo; `conta_demonstrativo` guarda só o que casa com as regras de
`mapeamento_siconfi.yaml`. Ver também `rastro.reconstrucao`.
"""

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

ARQUIVO_PADRAO = Path(__file__).with_name("mapeamento_siconfi.yaml")


def _casa(valor: str | None, padroes: list[str] | None) -> bool:
    if padroes is None:
        return True
    if valor is None:
        return False
    return any(valor.startswith(p[:-1]) if p.endswith("*") else valor == p for p in padroes)


@dataclass(frozen=True)
class Regra:
    anexo: str
    cod_conta: tuple[str, ...]
    conta: tuple[str, ...] | None = None
    rotulo: tuple[str, ...] | None = None
    colunas: tuple[str, ...] | None = None

    def aceita(self, linha: dict) -> bool:
        return (
            linha.get("anexo") == self.anexo
            and linha.get("cod_conta") in self.cod_conta
            and _casa(linha.get("conta"), self.conta and list(self.conta))
            and _casa(linha.get("rotulo"), self.rotulo and list(self.rotulo))
            and _casa(linha.get("coluna"), self.colunas and list(self.colunas))
        )


@dataclass(frozen=True)
class Mapeamento:
    versao: int
    hash: str
    regras: tuple[Regra, ...]

    def aceita(self, linha: dict) -> bool:
        return any(r.aceita(linha) for r in self.regras)


def _tupla(v) -> tuple[str, ...] | None:
    if v is None:
        return None
    return tuple(v) if isinstance(v, list) else (v,)


def carregar(caminho: Path = ARQUIVO_PADRAO) -> Mapeamento:
    bruto = caminho.read_bytes()
    dados = yaml.safe_load(bruto)
    regras = tuple(
        Regra(
            anexo=r["anexo"],
            cod_conta=_tupla(r["cod_conta"]),
            conta=_tupla(r.get("conta")),
            rotulo=_tupla(r.get("rotulo")),
            colunas=_tupla(r.get("colunas")),
        )
        for r in dados["regras"]
    )
    return Mapeamento(dados["versao"], hashlib.sha256(bruto).hexdigest()[:12], regras)


@lru_cache
def padrao() -> Mapeamento:
    return carregar()
