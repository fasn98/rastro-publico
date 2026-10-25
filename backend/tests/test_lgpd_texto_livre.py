"""LGPD: CPF citado no texto livre das proposições (correção de 15/10/2026).

Fixture real: `camara_proposicoes_2023_cpf_amostra.json`, os dois itens da API da Câmara
(/proposicoes, 2023, coletados em 09/10/2026) cujas ementas de denúncia trazem o CPF da
pessoa denunciada: PROC 508/2023 (id 2400894) e PROC 516/2023 (id 2405476). Pela regra das
fixtures, o CPF verdadeiro NÃO entra no repositório: a fixture já vem redigida, com
"[CPF removido]" no lugar do número.

Para exercitar o redator, os testes recolocam no lugar do marcador números que não são o
CPF de ninguém: onze dígitos iguais, que a regra do dígito verificador da Receita
declara inválidos. Assim a entrada tem a forma do texto original (com e sem pontuação)
sem trazer o dado pessoal.
"""

import csv
import gzip
import io
import json
import re
from datetime import UTC, datetime

import respx
from sqlalchemy import select
from test_cota_emendas import _zip_cota
from test_politicos import JSON, POL, _json

from rastro import site
from rastro.coletores.arquivo import ArquivoBruto, Redacao, ler_payload, sha256
from rastro.coletores.base import novo_cliente
from rastro.coletores.redacao import reaplicar_redacao, redigir_arquivadas
from rastro.models import PayloadBruto, RespostaBruta
from rastro.politicos import camara, lgpd
from rastro.politicos.comum import upsert_politico
from rastro.politicos.modelos import DEPUTADO_FEDERAL, PolProposicao

FIXTURE = "camara_proposicoes_2023_cpf_amostra.json"
REDIGIDA = json.loads(_json(FIXTURE))
# no lugar do CPF: a forma pontuada numa ementa, só dígitos na outra (nenhum é CPF válido)
NO_LUGAR = {"2400894": "111.111.111-11", "2405476": "22222222222"}
URL = f"{camara.API}/proposicoes"
CPF_OU_MARCADOR = re.compile(rb"111\.111\.111-11|22222222222")


def _como_veio_da_fonte() -> bytes:
    dados = json.loads(_json(FIXTURE))
    for item in dados["dados"]:
        item["ementa"] = item["ementa"].replace(lgpd.CPF_REMOVIDO, NO_LUGAR[str(item["id"])])
    return json.dumps(dados, ensure_ascii=False).encode()


def _deputado(session) -> int:
    pid = upsert_politico(
        session,
        {
            "fonte": "camara",
            "id_fonte": "221328",
            "cargo": DEPUTADO_FEDERAL,
            "nome": "Deputado da amostra",
            "uf": "SP",
            "legislatura": 57,
            "em_exercicio": True,
            "url_fonte": f"{camara.API}/deputados/221328",
            "url_pagina": "https://www.camara.leg.br/deputados/221328",
        },
    )
    session.commit()
    return pid


# ------------------------------------------------------------------ redator


def test_redator_troca_o_cpf_com_e_sem_pontuacao():
    red = lgpd.PROPOSICOES(_como_veio_da_fonte())
    assert json.loads(red.conteudo)["dados"] == REDIGIDA["dados"]
    assert red.campos_removidos == ["ementa (2 CPF)"]
    assert not CPF_OU_MARCADOR.search(red.conteudo)


def test_resposta_sem_cpf_fica_byte_a_byte_como_veio():
    original = _json("camara_proposicoes_204534_2025_p1.json")
    red = lgpd.PROPOSICOES(original)
    assert red.conteudo == original and red.campos_removidos == []


def test_cpf_parcialmente_pontuado_e_cnpj():
    assert lgpd.sem_cpf("n.111111111-11 e 111.111.11111") == (
        f"n.{lgpd.CPF_REMOVIDO} e {lgpd.CPF_REMOVIDO}"
    )
    # CNPJ (14 dígitos) e número de processo não são tocados
    for texto in ("CNPJ 12.345.678/0001-90", "CNPJ 12345678000190", "processo 2023.0001234"):
        assert lgpd.sem_cpf(texto) == texto


# ------------------------------------------------------------------ coleta


@respx.mock
def test_coleta_grava_banco_e_arquivo_sem_o_cpf(session, engine):
    original = _como_veio_da_fonte()
    respx.get(URL).respond(content=original, headers=JSON)
    pid = _deputado(session)
    with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
        assert camara.coletar_proposicoes(session, c, 221328, pid, 2023) == 2

    ementas = session.scalars(select(PolProposicao.ementa).order_by(PolProposicao.id_fonte)).all()
    assert ementas == [x["ementa"] for x in REDIGIDA["dados"]]
    resp = session.scalar(select(RespostaBruta))
    assert resp.sha256_original == sha256(original)  # a conferência com a fonte continua
    assert resp.campos_removidos == ["ementa (2 CPF)"]
    gravado = ler_payload(session.get(PayloadBruto, resp.sha256))
    assert not CPF_OU_MARCADOR.search(gravado)
    assert json.loads(gravado)["dados"] == REDIGIDA["dados"]


@respx.mock
def test_coleta_sem_cpf_arquiva_a_resposta_sem_redacao(session, engine):
    original = _json("camara_proposicoes_204534_2025_p1.json")
    respx.get(URL).respond(content=original, headers=JSON)
    pid = _deputado(session)
    with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
        camara.coletar_proposicoes(session, c, 221328, pid, 2025)
    resp = session.scalar(select(RespostaBruta))
    assert resp.sha256 == sha256(original) and resp.sha256_original is None
    assert resp.redacao is None and resp.campos_removidos is None


# ------------------------------------------------------- limpeza do que já foi gravado


@respx.mock
def test_limpeza_do_banco_e_do_arquivo_coletados_antes_da_regra(session, engine, monkeypatch):
    original = _como_veio_da_fonte()
    respx.get(URL).respond(content=original, headers=JSON)
    pid = _deputado(session)
    # como era antes de 15/10/2026: sem redator nas proposições e a ementa gravada inteira
    monkeypatch.setattr(lgpd, "PROPOSICOES", Redacao)
    monkeypatch.setattr(lgpd, "sem_cpf", lambda t: t)
    with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
        camara.coletar_proposicoes(session, c, 221328, pid, 2023)
    monkeypatch.undo()
    assert session.get(PayloadBruto, sha256(original)) is not None

    assert lgpd.limpar_cpf_nas_tabelas(session) == 2
    assert redigir_arquivadas(session, lgpd.REGRAS) == 1

    session.expire_all()
    ementas = session.scalars(select(PolProposicao.ementa).order_by(PolProposicao.id_fonte)).all()
    assert ementas == [x["ementa"] for x in REDIGIDA["dados"]]
    resp = session.scalar(select(RespostaBruta))
    assert resp.sha256_original == sha256(original) and resp.sha256 != sha256(original)
    assert resp.campos_removidos == ["ementa (2 CPF)"]
    assert "após a coleta" in resp.redacao
    # o conteúdo com o CPF saiu do arquivo; nenhum payload guarda o número
    assert session.get(PayloadBruto, sha256(original)) is None
    for p in session.scalars(select(PayloadBruto)):
        assert not CPF_OU_MARCADOR.search(ler_payload(p))
    # rodar de novo não muda nada
    assert lgpd.limpar_cpf_nas_tabelas(session) == 0
    assert redigir_arquivadas(session, lgpd.REGRAS) == 0


# ------------------------------------------------------------------ exportação


def test_verificar_recusa_cpf_em_arquivo_exportado(tmp_path):
    (tmp_path / "manifesto.json").write_text("{}")
    ementa = REDIGIDA["dados"][0]["ementa"].replace(lgpd.CPF_REMOVIDO, NO_LUGAR["2400894"])
    (tmp_path / "politicos").mkdir()
    (tmp_path / "politicos" / "1.json").write_text(json.dumps({"ementa": ementa}))
    assert site.verificar(tmp_path) == ["CPF no conteúdo (LGPD): politicos/1.json"]


def test_nenhuma_fixture_tem_cpf_formatado():
    padrao = re.compile(rb"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
    com_cpf = [
        str(f.relative_to(POL.parent))
        for f in POL.parent.rglob("*")
        if f.is_file() and padrao.search(f.read_bytes())
    ]
    assert com_cpf == []


# ------------------------------------------------- votações (arquivo anual da Câmara)


def _votacoes_com_cpf() -> bytes:
    """A amostra real de votações de 2025 com o número no lugar do CPF numa descrição, como
    na votação de 2023 cuja apresentação da proposição lista pessoas com o CPF."""
    linhas = list(csv.DictReader(io.StringIO(_json(VOTACOES).decode("utf-8-sig")), delimiter=";"))
    linhas[0]["ultimaApresentacaoProposicao_descricao"] += f" {NO_LUGAR['2405476']};"
    saida = io.StringIO()
    w = csv.DictWriter(saida, list(linhas[0]), delimiter=";", quoting=csv.QUOTE_ALL)
    w.writeheader()
    w.writerows(linhas)
    return ("﻿" + saida.getvalue()).encode()


VOTACOES = "camara_votacoes_2025_amostra.csv"


def test_votacoes_com_cpf_numa_descricao():
    red = lgpd.votacoes(_votacoes_com_cpf())
    assert red.campos_removidos == [
        "ultimaApresentacaoProposicao_descricao (CPF no texto) (1 linhas)"
    ]
    assert not CPF_OU_MARCADOR.search(red.conteudo)
    assert lgpd.CPF_REMOVIDO.encode() in red.conteudo


def test_votacoes_sem_cpf_ficam_byte_a_byte_como_vieram():
    original = _json(VOTACOES)
    assert lgpd.votacoes(original).conteudo == original
    assert lgpd.votacoes(original).campos_removidos == []


# ------------------------------------- cota redigida antes (pontuação parcial no nome)


def test_cota_ja_redigida_e_redigida_de_novo(session):
    # a cota real de 2025 (SP), redigida pela regra da coleta
    redigida = lgpd.cota(2025, "SP")(_zip_cota())
    linhas = list(csv.DictReader(io.StringIO(redigida.conteudo.decode()), delimiter=";"))
    pj = next(r for r in linhas if len(lgpd.digitos(r["txtCNPJCPF"])) == 14)
    # como ficou na cota gravada antes: o CPF com pontuação parcial colado ao nome de MEI
    pj["txtFornecedor"] += " 111111111-11"
    saida = io.StringIO()
    w = csv.DictWriter(
        saida, list(linhas[0]), delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\n"
    )
    w.writeheader()
    w.writerows(linhas)
    gravado = saida.getvalue().encode()
    url = camara.URL_COTA.format(ano=2025)
    session.add(
        PayloadBruto(
            sha256=sha256(gravado),
            tamanho=len(gravado),
            compressao="gzip",
            conteudo=gzip.compress(gravado, mtime=0),
        )
    )
    session.flush()
    resp = RespostaBruta(
        metodo="GET",
        url=url,
        status_http=200,
        recebido_em=datetime.now(UTC),
        sha256=sha256(gravado),
        tamanho=len(gravado),
        sha256_original="f" * 64,
        tamanho_original=1,
        campos_removidos=["cpf"],
        redacao="redação da coleta",
    )
    session.add(resp)
    session.commit()

    assert reaplicar_redacao(session, lgpd.REDIGIR_DE_NOVO) == 1
    session.refresh(resp)
    novo = ler_payload(session.get(PayloadBruto, resp.sha256))
    assert b"111111111-11" not in novo and lgpd.CPF_REMOVIDO.encode() in novo
    assert resp.sha256_original == "f" * 64  # continua o da fonte
    assert resp.campos_removidos == ["cpf", "txtFornecedor (CPF no nome) (1 linhas)"]
    assert resp.redacao.startswith("redação da coleta; ") and "redigido de novo" in resp.redacao
    assert session.get(PayloadBruto, sha256(gravado)) is None
    # sem nada a trocar, a cota gravada fica byte a byte como estava
    assert lgpd.COTA_GRAVADA(novo).conteudo == novo
    assert reaplicar_redacao(session, lgpd.REDIGIR_DE_NOVO) == 0


def test_link_do_documento_do_senado_nao_e_tocado():
    # matérias reais do Senado (2025) cujo link tem 11 dígitos seguidos dentro do código do
    # documento: não é CPF e não está num campo de texto livre
    original = _json("senado_processo_6342_2025_link_amostra.json")
    assert all(re.search(r"(?<!\d)\d{11}(?!\d)", x["urlDocumento"]) for x in json.loads(original))
    red = lgpd.PROPOSICOES(original)
    assert red.conteudo == original and red.campos_removidos == []
