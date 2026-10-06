import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_indicadores_novos import COD, coletado, ente  # noqa: F401 (fixtures)

from rastro import ranking as rk
from rastro.api.main import app
from rastro.db import get_session
from rastro.models import EnteSiconfi, NotaRanking


@pytest.mark.parametrize(
    ("valor", "pior", "melhor", "esperado"),
    [
        (5, 0, 10, 0.5),
        (-3, 0, 10, 0.0),
        (15, 0, 10, 1.0),
        (45, 54, 37.8, 9 / 16.2),
        (60, 54, 37.8, 0.0),
    ],
)
def test_normalizar(valor, pior, melhor, esperado):
    assert rk.normalizar(valor, pior, melhor) == pytest.approx(esperado)


def test_faixas_populacionais():
    faixas = rk.carregar_metodologia().regras["faixas"]
    assert rk.faixa_populacional(10_000, faixas) == "até 10 mil"
    assert rk.faixa_populacional(10_001, faixas) == "10 a 50 mil"
    assert rk.faixa_populacional(500_001, faixas) == "acima de 500 mil"
    assert rk.faixa_populacional(None, faixas) is None


def test_posicoes_com_empate():
    itens = [{"nota": 0.9}, {"nota": 0.7}, {"nota": 0.7}, {"nota": 0.5}, {"nota": None}]
    rk._posicoes(itens, "pos")
    assert [i.get("pos") for i in itens] == [1, 2, 2, 4, None]


def test_metodologia_versionada():
    met = rk.carregar_metodologia()
    assert met.versao == "1.0.0"
    assert len(met.hash) == 12
    assert met.exercicios == [2023, 2024, 2025]
    assert set(met.regras["indicadores"]) == {
        "autonomia", "pessoal", "liquidez", "investimento", "transparencia",
    }  # fmt: skip


def test_nota_de_adamantina(session, coletado):  # noqa: F811
    met = rk.carregar_metodologia()
    r = rk.avaliar(session, coletado, met)
    c = r["componentes"]
    # só 2025 coletado: 2023 e 2024 ficam fora da média (não contam como zero)
    assert c["autonomia"]["anos_com_dado"] == 1
    assert c["autonomia"]["nota"] == pytest.approx((4.3073 - 1) / 9, abs=1e-4)
    assert c["pessoal"]["nota"] == pytest.approx((54 - 50.82) / 16.2, abs=1e-4)
    assert c["liquidez"]["nota"] == 1.0  # 21,93% >= 20%
    assert c["investimento"]["nota"] == pytest.approx(0.19471, abs=1e-4)
    assert c["transparencia"]["nota"] == 1.0
    esperado = (0.36748 + 0.19630 + 1 + 0.19471 + 1) / 5
    assert r["nota"] == pytest.approx(esperado, abs=1e-4)
    assert r["indicadores_faltantes"] == 0
    assert r["faixa"] == "10 a 50 mil"


def test_sem_nota_abaixo_do_minimo_de_fiscais(session, ente):  # noqa: F811
    r = rk.avaliar(session, ente, rk.carregar_metodologia())
    assert r["nota"] is None
    assert r["indicadores_faltantes"] == 5


def test_peso_e_regras_vem_do_arquivo(session, coletado, tmp_path: Path):  # noqa: F811
    texto = rk.ARQUIVO_PADRAO.read_text().replace('versao = "1.0.0"', 'versao = "9.9.9"')
    # zera o peso da transparência (só na seção dela)
    inicio = texto.index("[indicadores.transparencia]")
    texto = texto[:inicio] + texto[inicio:].replace("peso = 1", "peso = 0", 1)
    arq = tmp_path / "m.toml"
    arq.write_text(texto)
    met = rk.carregar_metodologia(arq)
    r = rk.avaliar(session, coletado, met)
    # transparência com peso 0 não pesa na média
    esperado = (0.36748 + 0.19630 + 1 + 0.19471) / 4
    assert r["nota"] == pytest.approx(esperado, abs=1e-4)
    assert met.hash != rk.carregar_metodologia().hash


def test_calcular_grava_versao_e_api(session, coletado):  # noqa: F811
    session.add(EnteSiconfi(cod_ibge=3507209, nome="Borá", esfera="M", uf="SP", regiao="SE",
                            capital=False, populacao=932, exercicio=2026))  # fmt: skip
    session.commit()
    rk.calcular(session, "SP")
    notas = {n.cod_ibge: n for n in session.query(NotaRanking)}
    assert notas[COD].versao == "1.0.0" and notas[COD].posicao_geral == 1
    assert notas[3507209].nota is None and notas[3507209].posicao_geral is None

    app.dependency_overrides[get_session] = lambda: session
    try:
        api = TestClient(app)
        r = api.get("/api/ranking", params={"faixa": "10 a 50 mil"}).json()
        assert [i["nome"] for i in r["itens"]] == ["Adamantina"]
        assert r["versao"] == "1.0.0"

        texto = api.get("/api/ranking.csv").content.decode("utf-8-sig")
        linhas = list(csv.DictReader(io.StringIO(texto), delimiter=";"))
        assert [linha["municipio"] for linha in linhas] == ["Adamantina", "Borá"]
        assert linhas[0]["versao_metodologia"] == "1.0.0"
        assert linhas[1]["nota"] == ""  # sem nota

        d = api.get(f"/api/ranking/{COD}").json()
        assert (d["posicao_geral"], d["total_com_nota"], d["total_faixa"]) == (1, 1, 1)
        assert api.get("/api/metodologia").json()["versao"] == "1.0.0"
    finally:
        app.dependency_overrides.clear()
