"""API de auditoria em produção: CORS só para o site, cache longo e ETag."""

import hashlib

import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import FIXTURES
from rastro.api import auditoria
from rastro.coletores import ibge
from rastro.coletores.arquivo import ArquivoBruto
from rastro.coletores.base import get_json, novo_cliente
from rastro.db import get_session
from rastro.models import RespostaBruta


@pytest.fixture
def api(session, engine, monkeypatch):
    monkeypatch.setenv("RASTRO_CORS_ORIGENS", "https://fasn98.github.io,http://localhost:5173")
    from rastro.config import get_settings

    get_settings.cache_clear()
    app = auditoria.criar_app()
    app.dependency_overrides[get_session] = lambda: session
    auditoria.cache_payloads.limpar()
    bruto = (FIXTURES / "ibge_municipios.json").read_bytes()
    with respx.mock:
        respx.get(ibge.URL_MUNICIPIOS).respond(
            content=bruto, headers={"content-type": "application/json"}
        )
        with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
            get_json(c, ibge.URL_MUNICIPIOS)
    rid = session.scalars(select(RespostaBruta.id)).one()
    return TestClient(app), rid, bruto


def test_cors_so_para_o_site_e_localhost(api):
    cliente, rid, _ = api
    url = f"/api/respostas/{rid}/bruto"
    for origem in ("https://fasn98.github.io", "http://localhost:5173"):
        r = cliente.get(url, headers={"Origin": origem})
        assert r.headers["access-control-allow-origin"] == origem
    r = cliente.get(url, headers={"Origin": "https://exemplo-malicioso.com"})
    assert "access-control-allow-origin" not in r.headers
    # preflight de outra origem é recusado
    r = cliente.options(
        url,
        headers={"Origin": "https://exemplo-malicioso.com", "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 400


def test_cache_longo_e_etag(api):
    cliente, rid, bruto = api
    r = cliente.get(f"/api/respostas/{rid}/bruto")
    sha = hashlib.sha256(bruto).hexdigest()
    assert r.headers["etag"] == f'"{sha}"'
    assert "immutable" in r.headers["cache-control"]
    r2 = cliente.get(f"/api/respostas/{rid}/bruto", headers={"If-None-Match": f'"{sha}"'})
    assert r2.status_code == 304 and r2.content == b""


def test_so_os_endpoints_de_auditoria(api):
    cliente, rid, _ = api
    assert cliente.get("/api/saude").json() == {"status": "ok"}
    assert cliente.get("/").status_code == 200
    # o resto do portal é estático: a API de produção não expõe ranking, municípios etc.
    for rota in ("/api/ranking", "/api/municipios", "/api/politicos", "/api/metodologia"):
        assert cliente.get(rota).status_code == 404
    assert set(auditoria.app.openapi()["paths"]) == {
        "/api/respostas/{resposta_id}",
        "/api/respostas/{resposta_id}/bruto",
        "/api/demonstrativos/{demonstrativo_id}/respostas",
        "/api/bruto/{sha}",
        "/api/saude",
    }


def test_database_url_do_replit(monkeypatch):
    from rastro.config import get_settings

    monkeypatch.delenv("RASTRO_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep-x.neon.tech/neondb?sslmode=require")
    get_settings.cache_clear()
    assert get_settings().database_url == (
        "postgresql+psycopg://u:p@ep-x.neon.tech/neondb?sslmode=require"
    )
    monkeypatch.setenv("RASTRO_DATABASE_URL", "postgresql+psycopg://a:b@c/d")
    get_settings.cache_clear()
    assert get_settings().database_url == "postgresql+psycopg://a:b@c/d"  # explícito vence
    get_settings.cache_clear()


# --- resposta bruta pelo SHA-256 do conteúdo ------------------------------------------------


def test_bruto_por_hash_igual_ao_por_id_imutavel_e_com_etag(api):
    cliente, rid, bruto = api
    sha = hashlib.sha256(bruto).hexdigest()
    r = cliente.get(f"/api/bruto/{sha}", headers={"Origin": "https://fasn98.github.io"})
    assert r.status_code == 200
    assert r.content == bruto == cliente.get(f"/api/respostas/{rid}/bruto").content
    assert hashlib.sha256(r.content).hexdigest() == r.headers["x-rastro-sha256"] == sha
    assert r.headers["etag"] == f'"{sha}"'
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert r.headers["x-rastro-url-origem"] == ibge.URL_MUNICIPIOS
    assert r.headers["x-rastro-primeiro-recebimento"]
    assert "X-Rastro-Primeiro-Recebimento" in r.headers["access-control-expose-headers"]
    assert r.headers["content-type"].startswith("application/json")
    assert "x-rastro-sha256-original" not in r.headers  # sem redação: gravado = original
    assert r.headers["access-control-allow-origin"] == "https://fasn98.github.io"
    r2 = cliente.get(f"/api/bruto/{sha}", headers={"If-None-Match": f'"{sha}"'})
    assert r2.status_code == 304 and r2.content == b""


def test_bruto_por_hash_inexistente_ou_invalido(api):
    cliente, _, _ = api
    assert cliente.get(f"/api/bruto/{'0' * 64}").status_code == 404
    for invalido in ("abc", "G" * 64, "0" * 63, "A" * 64):
        assert cliente.get(f"/api/bruto/{invalido}").status_code == 422


def test_bruto_por_hash_redigido_lgpd(session, engine, api):
    from rastro.coletores.base import get_json_com_origem
    from rastro.politicos import lgpd, senado

    cliente, _, _ = api
    original = (FIXTURES / "politicos" / "senado_senadores_atual.json").read_bytes()
    url = f"{senado.API}/senador/lista/atual.json"
    with respx.mock:
        respx.get(url).respond(content=original, headers={"content-type": "application/json"})
        with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
            _, rid = get_json_com_origem(c, url, redator=lgpd.SENADO_LISTA)
    gravado = session.get(RespostaBruta, rid)
    r = cliente.get(f"/api/bruto/{gravado.sha256}")
    assert r.status_code == 200
    # devolve a versão gravada (sem o campo pessoal), nunca o original
    assert b"EmailParlamentar" not in r.content
    assert hashlib.sha256(r.content).hexdigest() == r.headers["x-rastro-sha256"]
    assert r.headers["x-rastro-sha256"] == gravado.sha256
    assert r.headers["x-rastro-sha256-original"] == hashlib.sha256(original).hexdigest()
    assert r.headers["x-rastro-campos-removidos"] == "EmailParlamentar"
    # o original não está no arquivo, então não há endereço por hash para ele
    assert cliente.get(f"/api/bruto/{hashlib.sha256(original).hexdigest()}").status_code == 404
