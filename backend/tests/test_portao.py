"""Portão de qualidade por UF (ADR-0020), com respostas reais gravadas do SICONFI.

Votuporanga/SP, 2024: extrato, RREO do 6º bimestre e RGF do 3º quadrimestre (respostas
conferidas na API em 08/10/2026). Nas conferências com a "fonte", o respx devolve a mesma
resposta gravada (confere) ou a resposta real de outro ente (divergência).
"""

from datetime import date

import httpx
import pytest
import respx
from sqlalchemy import select

from conftest import carregar
from rastro import portao
from rastro.coletores import siconfi_demonstrativos as sd
from rastro.coletores.arquivo import ArquivoBruto
from rastro.coletores.base import novo_cliente
from rastro.models import EnteSiconfi, PayloadBruto

VOTUPORANGA = 3557105
HOJE = date(2026, 10, 12)


def _rotas_votuporanga(rreo: str = "votuporanga_2024_rreo6.json", extrato=None):
    respx.get(sd.URL_EXTRATO).respond(json=carregar(extrato or "votuporanga_2024_extrato.json"))
    respx.get(sd.URL_RREO).respond(json=carregar(rreo))
    for poder in "EL":
        respx.get(sd.URL_RGF, params__contains={"co_poder": poder}).respond(
            json=carregar(f"votuporanga_2024_rgf3_{poder}.json")
        )


@pytest.fixture
def votuporanga(session, engine):
    e = EnteSiconfi(cod_ibge=VOTUPORANGA, nome="Votuporanga", esfera="M", uf="SP",
                    regiao="SE", capital=False, populacao=96795, exercicio=2026)  # fmt: skip
    session.add(e)
    session.commit()
    with respx.mock:
        _rotas_votuporanga()
        # com o arquivo bruto: a conferência dos hashes lê as respostas guardadas
        with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as client:
            sd.coletar_ente(session, client, e, 2024)
    return e


def _avaliar(session, **rotas):
    with respx.mock:
        _rotas_votuporanga(**rotas)
        with httpx.Client() as client:
            return portao.avaliar_uf(session, client, "SP", [2024], HOJE)


def test_uf_completa_e_que_confere_com_a_fonte_e_aprovada(session, votuporanga):
    r = _avaliar(session)
    assert r["aprovada"], r["motivos"]
    assert r["completude"] == {
        "entes": 1, "esperados": 1, "sem_extrato": 0, "com_falha": 0, "exemplos": []
    }  # fmt: skip
    assert r["arquivo_bruto"]["conferidas"] > 0 and r["arquivo_bruto"]["divergentes"] == []
    # o RREO comparado é o da Prefeitura, não o do consórcio com o mesmo código (D1)
    [sorteado] = r["sorteados"]
    assert sorteado["situacao"] == "confere" and sorteado["relatorio"] == "RREO 6B/2024"
    assert sorteado["celulas"] > 0


def test_fonte_diferente_do_banco_reprova(session, votuporanga):
    # a "fonte" devolve o RREO real de outro ente: nenhuma célula da Prefeitura confere
    r = _avaliar(session, rreo="siconfi_rreo_simplificado.json")
    assert not r["aprovada"]
    assert "célula(s) diferente(s) da fonte" in r["motivos"][0]


def test_relatorio_que_sumiu_do_extrato_da_fonte_reprova(session, votuporanga):
    # extrato real de outro ente (Gastão Vidigal, 2024): o RREO 6B completo de Votuporanga
    # não aparece nele (lá o 6º bimestre é o RREO Simplificado)
    r = _avaliar(session, extrato="gastao_vidigal_2024_extrato.json")
    assert not r["aprovada"]
    assert r["motivos"] == [
        "Votuporanga (3557105), RREO 6B/2024: não consta mais no extrato da fonte"
    ]


def test_ente_sem_extrato_lido_reprova_a_uf(session, votuporanga):
    session.add(
        EnteSiconfi(
            cod_ibge=3500105,
            nome="Adamantina",
            esfera="M",
            uf="SP",
            regiao="SE",
            capital=False,
            exercicio=2026,
        )  # fmt: skip
    )
    session.commit()
    r = _avaliar(session)
    assert not r["aprovada"]
    assert r["completude"]["sem_extrato"] == 1
    assert r["completude"]["exemplos"] == ["3500105/2024"]
    assert "sorteados" not in r  # incompleta: nem consulta a fonte


def test_arquivo_bruto_corrompido_reprova(session, votuporanga):
    # simula uma falha de armazenamento: os bytes guardados deixam de bater com o SHA-256
    for p in session.scalars(select(PayloadBruto)):
        p.conteudo = p.conteudo[:-1]
    session.commit()
    r = _avaliar(session)
    assert not r["aprovada"]
    assert "SHA-256 que não confere" in r["motivos"][0]


def test_sorteio_e_repetivel_pela_data_e_pela_uf(session, votuporanga):
    a = _avaliar(session)
    b = _avaliar(session)
    assert a["sorteados"] == b["sorteados"]


def test_uf_sem_entes_e_reprovada(session):
    with httpx.Client() as client:
        r = portao.avaliar_uf(session, client, "RR", [2024], HOJE)
    assert not r["aprovada"] and r["motivos"] == ["nenhum ente da UF no cadastro do SICONFI"]
