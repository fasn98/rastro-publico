"""Redação LGPD das fontes do módulo de políticos.

Nenhum CPF, data de nascimento, título de eleitor ou e-mail pode existir nas tabelas nem
no arquivo de respostas brutas. As regras abaixo valem na coleta (o redator vai na
requisição) e para respostas já arquivadas (`rastro redigir-respostas`).
"""

import json
import re
from collections.abc import Iterable

from rastro.coletores.arquivo import Redacao
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


# CPF no meio de um texto (razão social de MEI "NOME 12345678901", ementa de denúncia
# "inscrito no CPF sob o n° 000.000.000-00"): 11 dígitos com ou sem a pontuação, completa
# ou parcial, sem outro dígito encostado (não pega CNPJ, que tem 14 dígitos)
_CPF_NO_TEXTO = re.compile(r"(?<!\d)(?<!\d\.)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
# o mesmo padrão, para filtrar candidatos no PostgreSQL (o filtro fino é o de cima)
CPF_NO_TEXTO_SQL = r"[0-9]{3}\.?[0-9]{3}\.?[0-9]{3}-?[0-9]{2}"
CPF_REMOVIDO = "[CPF removido]"


def sem_cpf(texto: str | None) -> str | None:
    return _CPF_NO_TEXTO.sub(CPF_REMOVIDO, texto) if texto else texto


# Campos de texto livre das proposições (Câmara: ementa; Senado: ementa e autoria). Os
# demais são códigos, datas e links: o link do documento no Senado tem 11 dígitos seguidos
# ("...documento?dm=...") e não pode ser tocado.
TEXTO_LIVRE = frozenset({"ementa", "autoria"})


def cpf_em_texto_livre(original: bytes) -> Redacao:
    """Redator de JSON das proposições da Câmara e das matérias do Senado: troca o CPF
    citado nos campos de texto livre (`TEXTO_LIVRE`) por "[CPF removido]". Sem CPF,
    devolve os bytes originais intactos (e o arquivo grava a resposta como veio)."""
    trocas: dict[str, int] = {}

    def limpar(no, chave="(raiz)"):
        if isinstance(no, dict):
            return {k: limpar(v, k) for k, v in no.items()}
        if isinstance(no, list):
            return [limpar(v, chave) for v in no]
        if isinstance(no, str) and chave in TEXTO_LIVRE:
            novo, n = _CPF_NO_TEXTO.subn(CPF_REMOVIDO, no)
            if n:
                trocas[chave] = trocas.get(chave, 0) + n
            return novo
        return no

    dados = limpar(json.loads(original))
    if not trocas:
        return Redacao(original)
    campos = [f"{k} ({n} CPF)" for k, n in sorted(trocas.items())]
    return Redacao(
        json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode(),
        campos,
        "JSON regravado com o CPF citado no texto trocado por "
        f"{CPF_REMOVIDO!r}: {', '.join(campos)}",
    )


# Câmara /proposicoes e Senado /processo: ementa e autoria são texto livre
PROPOSICOES = cpf_em_texto_livre


def _descricoes_sem_cpf(linha: dict) -> list[str]:
    alterados = []
    for k, v in linha.items():
        if k and k.lower().endswith("descricao") and v:
            limpo = sem_cpf(v)
            if limpo != v:
                linha[k] = limpo
                alterados.append(f"{k} (CPF no texto)")
    return alterados


_VOTACOES_CSV = redator_csv((), transformar=_descricoes_sem_cpf)


def votacoes(original: bytes) -> Redacao:
    """Câmara, votacoes-{ano}.csv: a descrição da apresentação da proposição pode listar
    pessoas com o CPF. Troca o CPF nas colunas de descrição; sem CPF, os bytes originais."""
    red = _VOTACOES_CSV(original)
    return red if red.campos_removidos else Redacao(original)


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


# Cota já gravada redigida (CSV em UTF-8, sem as colunas pessoais): de novo o CPF no nome
# do fornecedor, com o padrão atual (o anterior não pegava a pontuação parcial)
COTA_GRAVADA = redator_csv((), encoding="utf-8", transformar=apagar_pessoa_fisica)


URL_PROPOSICOES = (
    r"^https://(dadosabertos\.camara\.leg\.br/api/v2/proposicoes"
    r"|legis\.senado\.leg\.br/dadosabertos/processo)\?"
)
URL_VOTACOES = r"^https://dadosabertos\.camara\.leg\.br/arquivos/votacoes/csv/votacoes-\d{4}\.csv$"
REGRAS = [
    (r"^https://dadosabertos\.camara\.leg\.br/api/v2/deputados(\?|$)", CAMARA_DEPUTADOS),
    # histórico do deputado: traz o e-mail de gabinete em cada evento
    (r"^https://dadosabertos\.camara\.leg\.br/api/v2/deputados/\d+/historico", CAMARA_DEPUTADOS),
    (r"^https://legis\.senado\.leg\.br/dadosabertos/senador/lista/", SENADO_LISTA),
    (URL_PROPOSICOES, PROPOSICOES),
    (URL_VOTACOES, votacoes),
]

# Respostas que já tinham sido redigidas por uma regra anterior e precisam de nova redação
# (`reaplicar_redacao`): a cota gravada antes de o CPF no nome do fornecedor ser apagado
REDIGIR_DE_NOVO = [(r"^https://www\.camara\.leg\.br/cotas/Ano-\d{4}\.csv\.zip$", COTA_GRAVADA)]


def limpar_cpf_nas_tabelas(session) -> int:
    """Troca o CPF citado no texto já gravado (coletas anteriores à regra de 15/10/2026):
    ementas e autoria das proposições, descrição das votações, nome do fornecedor da cota.
    Devolve quantas linhas mudaram; o arquivo bruto fica com `redigir_arquivadas` e
    `reaplicar_redacao`."""
    from sqlalchemy import or_, select

    from rastro.politicos.modelos import PolDespesaCota, PolProposicao, PolVotacao

    n = 0
    for modelo, campos in (
        (PolProposicao, ("ementa", "autoria")),
        (PolVotacao, ("descricao",)),
        (PolDespesaCota, ("fornecedor",)),
    ):
        colunas = [getattr(modelo, c) for c in campos]
        linhas = session.scalars(
            select(modelo).where(or_(*(c.regexp_match(CPF_NO_TEXTO_SQL) for c in colunas)))
        ).all()
        for linha in linhas:
            mudou = False
            for c in campos:
                limpo = sem_cpf(getattr(linha, c))
                if limpo != getattr(linha, c):
                    setattr(linha, c, limpo)
                    mudou = True
            n += mudou
    session.commit()
    return n
