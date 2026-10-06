"""Travas de publicação: dados novos só aparecem nas telas depois de validados.

Os dados podem ser coletados e conferidos antes (pela API de auditoria e pelo banco),
mas a API pública só os mostra quando a variável correspondente for "1".
- RASTRO_POL_PUBLICAR_TSE: eleitos do TSE (prefeitos, vereadores, governador,
  deputados estaduais), depois de conferidas as colunas e o cruzamento TSE <-> IBGE.
- RASTRO_POL_PUBLICAR_EMENDAS: emendas, depois de conferido o cruzamento de
  `localidadeDoGasto` com o código IBGE.
"""

import os


def _ligado(nome: str) -> bool:
    return os.environ.get(nome, "") == "1"


def tse() -> bool:
    return _ligado("RASTRO_POL_PUBLICAR_TSE")


def emendas() -> bool:
    return _ligado("RASTRO_POL_PUBLICAR_EMENDAS")
