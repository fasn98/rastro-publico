"""Varredura LGPD (scripts/varrer_lgpd.py): separa o CPF pontuado pelo dígito verificador e
põe à parte os campos que são identificador, hash, código ou link.

Os nomes de campo são os reais das tabelas e das fontes (Câmara, Senado, TSE). Os números
de 11 dígitos são o exemplo de documentação "123.456.789" com os verificadores calculados
aqui e sequências de dígitos iguais (não são CPF): nenhum CPF verdadeiro.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import varrer_lgpd as v  # noqa: E402
from test_lgpd_cota import SO_DIGITOS  # noqa: E402

PONTUADO = f"{SO_DIGITOS[:3]}.{SO_DIGITOS[3:6]}.{SO_DIGITOS[6:9]}-{SO_DIGITOS[9:]}"


def test_cpf_pontuado_separado_pelo_digito_verificador():
    assert v.achados(f"inscrito no CPF sob o n° {PONTUADO}") == {"cpf_formatado_dv_valido": 1}
    # pontuação parcial, verificador inválido (dígitos iguais não são CPF)
    assert v.achados("NOME 000000000-00 e 000.000.00000") == {"cpf_formatado_dv_invalido": 2}
    assert v.achados(f"doc {SO_DIGITOS}") == {"cpf_11_digitos_dv_valido": 1}
    assert v.achados("doc 00000000000") == {"11_digitos_dv_invalido": 1}


def test_identificadores_saem_a_parte():
    for campo in (
        "resposta_bruta.sha256",
        "resposta_bruta.sha256_original",
        "payload_bruto.sha256",
        "pol_politico.id_fonte",
        "pol_proposicao.url_pagina",
        "urlDocumento",
        "uri",
        "SQ_CANDIDATO",
        "SQ_COLIGACAO",
        "zip:ideDocumento",
        "ultimaApresentacaoProposicao_idProposicao",
    ):
        assert v.identificador(campo), campo
    for campo in (
        "pol_proposicao.ementa",
        "pol_proposicao.autoria",
        "pol_despesa_cota.fornecedor",
        "pol_despesa_cota.numero_documento",
        "zip:txtNumero",
        "zip:txtFornecedor",
        "ultimaApresentacaoProposicao_descricao",
        "(conteúdo)",
    ):
        assert not v.identificador(campo), campo
