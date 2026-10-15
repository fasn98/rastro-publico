"""LGPD na cota parlamentar: CPF no número do documento e e-mail no nome do fornecedor
(decisão do Fabio em 15/10/2026, depois da varredura de LGPD).

Fixture real: `camara_cota_2025_SP_160548.csv`, as 928 linhas de 2025 do deputado 160548
extraídas do Ano-2025.csv oficial. Ela tem 10 números de documento com 11 dígitos, e
nenhum passa no dígito verificador do CPF: são os casos reais que precisam ficar.

Os casos que precisam sair (CPF no número do documento, e-mail no nome) não entram no
repositório com o valor verdadeiro. No lugar deles, o teste põe, em linhas reais da
fixture, o número de exemplo de documentação "123.456.789" com os dígitos verificadores
calculados aqui pela regra do CPF (não está escrito no repositório como CPF) e um e-mail
no domínio reservado `.invalid` (RFC 2606), que não existe. Sequência de dígitos iguais
não serve: a Receita não a emite, e ela fica (há "00000000000" como número de documento
nos arquivos oficiais de 2023 e 2024).
"""

import csv
import io
import re
import zipfile

import respx
from sqlalchemy import func, select
from test_cota_emendas import CABECALHO_COTA
from test_politicos import POL

from rastro.coletores.arquivo import ArquivoBruto, ler_payload, sha256
from rastro.coletores.base import novo_cliente
from rastro.coletores.redacao import reaplicar_redacao
from rastro.models import PayloadBruto, RespostaBruta
from rastro.politicos import camara, lgpd
from rastro.politicos.comum import upsert_politico
from rastro.politicos.modelos import DEPUTADO_FEDERAL, PolDespesaCota

FIXTURE = "camara_cota_2025_SP_160548.csv"


def _com_verificador(base: str) -> str:
    """Os 9 primeiros dígitos mais os 2 verificadores do CPF (módulo 11)."""
    d = base
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        d += str((soma * 10) % 11 % 10)
    return d


SO_DIGITOS = _com_verificador("123456789")
CPF_NO_DOCUMENTO = f"{SO_DIGITOS[:3]}.{SO_DIGITOS[3:6]}.{SO_DIGITOS[6:9]}-{SO_DIGITOS[9:]}"
EMAIL_NO_NOME = "contato@marcador-de-teste.invalid"
URL = camara.URL_COTA.format(ano=2025)


def _linhas() -> list[dict]:
    return list(csv.DictReader(io.StringIO((POL / FIXTURE).read_text()), delimiter=";"))


ONZE_REAIS = sorted({r["txtNumero"] for r in _linhas() if re.fullmatch(r"\d{11}", r["txtNumero"])})


def _zip(com_casos: bool = True) -> bytes:
    """Ano-2025.csv.zip no layout oficial com as linhas reais do 160548 (as colunas
    pessoais voltam vazias, como em test_site._zip_cota) e, em duas linhas de pessoa
    jurídica, o CPF no número do documento e o e-mail no nome do fornecedor."""
    linhas = _linhas()
    if com_casos:
        pj = [r for r in linhas if len(lgpd.digitos(r["txtCNPJCPF"])) == 14]
        pj[0]["txtNumero"] = CPF_NO_DOCUMENTO
        pj[1]["txtFornecedor"] += f" {EMAIL_NO_NOME}"
    saida = io.StringIO()
    w = csv.DictWriter(saida, CABECALHO_COTA, delimiter=";", quoting=csv.QUOTE_ALL, restval="")
    w.writeheader()
    w.writerows(linhas)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Ano-2025.csv", saida.getvalue().encode("utf-8-sig"))
    return buf.getvalue()


def _mapa(session) -> dict[int, int]:
    pid = upsert_politico(
        session,
        {
            "fonte": "camara",
            "id_fonte": "160548",
            "cargo": DEPUTADO_FEDERAL,
            "nome": "Deputado da amostra",
            "uf": "SP",
            "legislatura": 57,
            "em_exercicio": True,
            "url_fonte": f"{camara.API}/deputados/160548",
            "url_pagina": "https://www.camara.leg.br/deputados/160548",
        },
    )
    session.commit()
    return {160548: pid}


def _sem_os_casos(conteudo: bytes) -> bool:
    return CPF_NO_DOCUMENTO.encode() not in conteudo and EMAIL_NO_NOME.encode() not in conteudo


# ------------------------------------------------------------------ regras


def test_numero_do_documento_so_sai_quando_e_cpf():
    assert len(ONZE_REAIS) == 10  # os números reais de 11 dígitos da fixture
    assert not any(lgpd.cpf_valido(n) for n in ONZE_REAIS)
    assert [lgpd.sem_cpf_valido(n) for n in ONZE_REAIS] == ONZE_REAIS
    for cpf in (CPF_NO_DOCUMENTO, SO_DIGITOS, f"{SO_DIGITOS[:9]}-{SO_DIGITOS[9:]}"):
        assert lgpd.sem_cpf_valido(cpf) == lgpd.CPF_REMOVIDO
    errado = SO_DIGITOS[:10] + str((int(SO_DIGITOS[10]) + 1) % 10)
    assert lgpd.sem_cpf_valido(errado) == errado  # verificador errado: fica
    # dígitos iguais passam na conta, mas não são CPF: ficam (como nos arquivos oficiais)
    for repetido in ("00000000000", "11111111111"):
        assert lgpd.sem_cpf_valido(repetido) == repetido


def test_email_no_nome_do_fornecedor():
    assert lgpd.fornecedor_sem_dados_pessoais(f"EMPRESA LTDA {EMAIL_NO_NOME}") == (
        f"EMPRESA LTDA {lgpd.EMAIL_REMOVIDO}"
    )
    assert lgpd.fornecedor_sem_dados_pessoais("EMPRESA LTDA") == "EMPRESA LTDA"
    # 11 dígitos antes do "@": o e-mail sai inteiro, sem sobrar o domínio
    com_digitos = "EMPRESA LTDA contato00000000000@marcador-de-teste.invalid"
    assert lgpd.fornecedor_sem_dados_pessoais(com_digitos) == (
        f"EMPRESA LTDA {lgpd.EMAIL_REMOVIDO}"
    )
    linha = {"txtCNPJCPF": "", "txtFornecedor": com_digitos, "txtNumero": ""}
    assert lgpd.apagar_pessoa_fisica(linha) == ["txtFornecedor (e-mail no nome)"]
    assert linha["txtFornecedor"] == f"EMPRESA LTDA {lgpd.EMAIL_REMOVIDO}"


# ------------------------------------------------------------------ coleta


@respx.mock
def test_coleta_da_cota_tira_cpf_do_documento_e_email_do_nome(session, engine):
    original = _zip()
    respx.get(URL).respond(content=original)
    mapa = _mapa(session)
    with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
        assert camara.coletar_cota(session, c, 2025, "SP", mapa) == 928

    numeros = set(session.scalars(select(PolDespesaCota.numero_documento)))
    assert lgpd.CPF_REMOVIDO in numeros and set(ONZE_REAIS) <= numeros
    assert CPF_NO_DOCUMENTO not in numeros
    com_email = select(func.count()).where(PolDespesaCota.fornecedor.like("%[e-mail removido]"))
    assert session.scalar(com_email) == 1

    resp = session.scalar(select(RespostaBruta))
    assert resp.sha256_original == sha256(original)
    assert "txtNumero (CPF) (1 linhas)" in resp.campos_removidos
    assert "txtFornecedor (e-mail no nome) (1 linhas)" in resp.campos_removidos
    gravado = ler_payload(session.get(PayloadBruto, resp.sha256))
    assert _sem_os_casos(gravado)
    assert all(n.encode() in gravado for n in ONZE_REAIS)  # os demais números ficam


# ------------------------------------------------------- limpeza do que já foi gravado


@respx.mock
def test_limpeza_da_cota_gravada_antes_da_regra(session, engine, monkeypatch):
    respx.get(URL).respond(content=_zip())
    mapa = _mapa(session)
    # como era antes da regra: número do documento e nome do fornecedor gravados inteiros
    monkeypatch.setattr(lgpd, "sem_cpf_valido", lambda t: t)
    monkeypatch.setattr(lgpd, "sem_email", lambda t: t)
    with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
        camara.coletar_cota(session, c, 2025, "SP", mapa)
    monkeypatch.undo()
    resp = session.scalar(select(RespostaBruta))
    antes = resp.sha256
    original, campos = resp.sha256_original, list(resp.campos_removidos)
    assert not _sem_os_casos(ler_payload(session.get(PayloadBruto, antes)))

    assert lgpd.limpar_cpf_nas_tabelas(session) == 2
    assert reaplicar_redacao(session, lgpd.REDIGIR_DE_NOVO) == 1

    session.expire_all()
    numeros = set(session.scalars(select(PolDespesaCota.numero_documento)))
    assert CPF_NO_DOCUMENTO not in numeros and set(ONZE_REAIS) <= numeros
    nomes = " ".join(n or "" for n in session.scalars(select(PolDespesaCota.fornecedor)))
    assert EMAIL_NO_NOME not in nomes and lgpd.EMAIL_REMOVIDO in nomes
    resp = session.scalar(select(RespostaBruta))
    assert resp.sha256_original == original  # continua o hash dos bytes da fonte
    assert resp.sha256 != antes and session.get(PayloadBruto, antes) is None
    assert resp.campos_removidos == [
        *campos,
        "txtFornecedor (e-mail no nome) (1 linhas)",
        "txtNumero (CPF) (1 linhas)",
    ]
    assert "redigido de novo" in resp.redacao
    for p in session.scalars(select(PayloadBruto)):
        assert _sem_os_casos(ler_payload(p))
    # rodar de novo não muda nada
    assert lgpd.limpar_cpf_nas_tabelas(session) == 0
    assert reaplicar_redacao(session, lgpd.REDIGIR_DE_NOVO) == 0
