import pytest
from fastapi.testclient import TestClient

from conftest import carregar
from rastro.api.main import app
from rastro.coletores import ibge, siconfi
from rastro.db import get_session
from rastro.models import EnteSiconfi, Municipio


@pytest.fixture
def client(session):
    session.add_all(Municipio(**ibge.normalizar(m)) for m in carregar("ibge_municipios.json"))
    session.add_all(
        EnteSiconfi(**siconfi.normalizar(e)) for e in carregar("siconfi_entes.json")["items"]
    )
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_lista_municipios_por_uf(client):
    r = client.get("/api/municipios", params={"uf": "sp"})
    assert r.status_code == 200
    assert r.json()["total"] == 2
    assert [m["nome"] for m in r.json()["itens"]] == ["Adamantina", "São Paulo"]


def test_busca_por_nome_ignora_acento(client):
    r = client.get("/api/municipios", params={"nome": "esperanca"})
    assert [m["cod_ibge"] for m in r.json()["itens"]] == [5101837]


def test_detalhe_inclui_ente_siconfi(client):
    r = client.get("/api/municipios/3550308")
    assert r.status_code == 200
    assert r.json()["ente_siconfi"]["capital"] is True


def test_detalhe_inexistente(client):
    assert client.get("/api/municipios/9999999").status_code == 404


def test_demonstrativos_e_contas(client, session):
    from datetime import UTC, datetime
    from decimal import Decimal

    from rastro.models import ContaDemonstrativo, DemonstrativoSiconfi

    d = DemonstrativoSiconfi(
        cod_ibge=3550308, exercicio=2025, demonstrativo="RGF", periodicidade="Q", periodo=3,
        poder="E", instituicao="Prefeitura Municipal de São Paulo - SP",
        data_status=datetime(2026, 1, 30, tzinfo=UTC), linhas=1,
        contas=[
            ContaDemonstrativo(
                anexo="RGF-Anexo 01", rotulo="Padrão", coluna="<MR-11>",
                cod_conta="DespesaComPessoalBruta", conta="DESPESA BRUTA COM PESSOAL (I)",
                valor=Decimal("3033403573.83"),
            )
        ],
    )  # fmt: skip
    session.add(d)
    session.commit()

    r = client.get("/api/entes/3550308/demonstrativos", params={"exercicio": 2025})
    assert [x["demonstrativo"] for x in r.json()] == ["RGF"]

    r = client.get(f"/api/demonstrativos/{d.id}/contas", params={"anexo": "RGF-Anexo 01"})
    assert r.json()[0]["valor"] == "3033403573.83"
    assert client.get("/api/demonstrativos/999999/contas").status_code == 404


def test_indicadores_404_sem_dados(client):
    assert client.get("/api/entes/3550308/indicadores").status_code == 404
