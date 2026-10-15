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


def cpf_valido(numero: str) -> bool:
    """11 dígitos cujos dois dígitos verificadores batem com a regra do CPF (módulo 11).
    Sequências de dígitos iguais passam na conta, mas a Receita não as emite e não são CPF:
    na cota aparecem como número de documento ("00000000000", 5 linhas em 2023 e 2024)."""
    d = digitos(numero)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10) % 11 % 10 != int(d[n]):
            return False
    return True


def sem_cpf_valido(texto: str | None) -> str | None:
    """Como `sem_cpf`, mas só troca o que passa no dígito verificador do CPF (número do
    documento fiscal da cota: os demais números de 11 dígitos são mantidos)."""
    if not texto:
        return texto
    return _CPF_NO_TEXTO.sub(lambda m: CPF_REMOVIDO if cpf_valido(m[0]) else m[0], texto)


_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
EMAIL_REMOVIDO = "[e-mail removido]"


def sem_email(texto: str | None) -> str | None:
    return _EMAIL.sub(EMAIL_REMOVIDO, texto) if texto else texto


def fornecedor_sem_dados_pessoais(texto: str | None) -> str | None:
    """Nome de fornecedor da cota (pessoa jurídica): sem CPF nem e-mail no meio do nome."""
    return sem_email(sem_cpf(texto))


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
    alterados = []
    if len(digitos(linha.get("txtCNPJCPF"))) == 11:
        linha["txtCNPJCPF"] = ""
        linha["txtFornecedor"] = ""
        alterados += ["txtCNPJCPF", "txtFornecedor"]
    else:
        nome = linha.get("txtFornecedor")
        sem_o_cpf = sem_cpf(nome)
        if sem_o_cpf != nome:
            alterados.append("txtFornecedor (CPF no nome)")
        limpo = sem_email(sem_o_cpf)
        if limpo != sem_o_cpf:
            alterados.append("txtFornecedor (e-mail no nome)")
        if alterados:
            linha["txtFornecedor"] = limpo
    # número do documento fiscal: só o que é CPF (dígito verificador válido) sai
    numero = linha.get("txtNumero")
    limpo = sem_cpf_valido(numero)
    if limpo != numero:
        linha["txtNumero"] = limpo
        alterados.append("txtNumero (CPF)")
    return alterados


def cota(ano: int, ufs: str | Iterable[str]):
    siglas = sorted({ufs} if isinstance(ufs, str) else set(ufs))
    return redator_csv(
        COTA_COLUNAS,
        filtro=lambda linha: linha["sgUF"] in siglas,
        descricao_filtro=f"só sgUF={','.join(siglas)}",
        membro_zip=f"Ano-{ano}.csv",
        transformar=apagar_pessoa_fisica,
    )


# Cota já gravada redigida (CSV em UTF-8, sem as colunas pessoais): de novo a regra atual
# (CPF com pontuação parcial e e-mail no nome do fornecedor, CPF no número do documento)
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


# limpeza por coluna (as demais: `sem_cpf`)
_LIMPEZA = {
    "fornecedor": fornecedor_sem_dados_pessoais,
    "numero_documento": sem_cpf_valido,
}


def limpar_cpf_nas_tabelas(session) -> int:
    """Troca o CPF citado no texto já gravado (coletas anteriores às regras de 15/10/2026):
    ementas e autoria das proposições, descrição das votações, nome do fornecedor da cota
    (também o e-mail) e número do documento da cota (só CPF com dígito verificador válido).
    Devolve quantas linhas mudaram; o arquivo bruto fica com `redigir_arquivadas` e
    `reaplicar_redacao`."""
    from sqlalchemy import or_, select

    from rastro.politicos.modelos import PolDespesaCota, PolProposicao, PolVotacao

    n = 0
    for modelo, campos in (
        (PolProposicao, ("ementa", "autoria")),
        (PolVotacao, ("descricao",)),
        (PolDespesaCota, ("fornecedor", "numero_documento")),
    ):
        colunas = [getattr(modelo, c) for c in campos]
        linhas = session.scalars(
            select(modelo).where(or_(*(c.regexp_match(f"{CPF_NO_TEXTO_SQL}|@") for c in colunas)))
        ).all()
        for linha in linhas:
            mudou = False
            for c in campos:
                limpo = _LIMPEZA.get(c, sem_cpf)(getattr(linha, c))
                if limpo != getattr(linha, c):
                    setattr(linha, c, limpo)
                    mudou = True
            n += mudou
    session.commit()
    return n
