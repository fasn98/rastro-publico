"""Redação LGPD das fontes do módulo de políticos.

Nenhum CPF, data de nascimento, título de eleitor ou e-mail pode existir nas tabelas nem
no arquivo de respostas brutas. As regras abaixo valem na coleta (o redator vai na
requisição) e para respostas já arquivadas (`rastro redigir-respostas`).
"""

import re
from collections.abc import Iterable

from rastro.coletores.redacao import redator_csv, redator_json

# Câmara, /deputados (listas): e-mail de gabinete
CAMARA_DEPUTADOS = redator_json({"email"})
# Senado, /senador/lista/*: e-mail de gabinete
SENADO_LISTA = redator_json({"EmailParlamentar"})

# Câmara, cota parlamentar (arquivo anual): CPF e carteira do deputado, passageiros;
# CPF e nome de fornecedor pessoa física (11 dígitos em txtCNPJCPF)
COTA_COLUNAS = ("cpf", "nuCarteiraParlamentar", "txtPassageiro")


def digitos(texto: str | None) -> str:
    return "".join(c for c in (texto or "") if c.isdigit())


# CPF isolado no meio de um texto (ex.: razão social de MEI "NOME 12345678901"):
# 11 dígitos sem outro dígito encostado (não pega CNPJ, que tem 14), ou no formato 000.000.000-00
_CPF_NO_TEXTO = re.compile(r"(?<!\d)\d{11}(?!\d)|(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
CPF_REMOVIDO = "[CPF removido]"


def sem_cpf(texto: str | None) -> str | None:
    return _CPF_NO_TEXTO.sub(CPF_REMOVIDO, texto) if texto else texto


def apagar_pessoa_fisica(linha: dict) -> list[str]:
    if len(digitos(linha.get("txtCNPJCPF"))) == 11:
        linha["txtCNPJCPF"] = ""
        linha["txtFornecedor"] = ""
        return ["txtCNPJCPF", "txtFornecedor"]
    limpo = sem_cpf(linha.get("txtFornecedor"))
    if limpo != linha.get("txtFornecedor"):
        linha["txtFornecedor"] = limpo
        return ["txtFornecedor (CPF no nome)"]
    return []


def cota(ano: int, ufs: str | Iterable[str]):
    siglas = sorted({ufs} if isinstance(ufs, str) else set(ufs))
    return redator_csv(
        COTA_COLUNAS,
        filtro=lambda linha: linha["sgUF"] in siglas,
        descricao_filtro=f"só sgUF={','.join(siglas)}",
        membro_zip=f"Ano-{ano}.csv",
        transformar=apagar_pessoa_fisica,
    )


REGRAS = [
    (r"^https://dadosabertos\.camara\.leg\.br/api/v2/deputados(\?|$)", CAMARA_DEPUTADOS),
    # histórico do deputado: traz o e-mail de gabinete em cada evento
    (r"^https://dadosabertos\.camara\.leg\.br/api/v2/deputados/\d+/historico", CAMARA_DEPUTADOS),
    (r"^https://legis\.senado\.leg\.br/dadosabertos/senador/lista/", SENADO_LISTA),
]
