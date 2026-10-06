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
