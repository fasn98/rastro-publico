import gzip
import hashlib
import json

import httpx
import respx
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from conftest import FIXTURES
from rastro.api.main import app
from rastro.coletores import ibge, siconfi
from rastro.coletores.base import executar, get_json, gravar_respostas
from rastro.db import get_session
from rastro.models import Coleta, ConteudoBruto, RespostaBruta

IBGE = (FIXTURES / "ibge_municipios.json").read_bytes()
ENTES = (FIXTURES / "siconfi_entes.json").read_bytes()
JSON = {"content-type": "application/json;charset=UTF-8"}


def _corpo(session, resposta: RespostaBruta) -> bytes:
    return gzip.decompress(session.get(ConteudoBruto, resposta.sha256_gravado).corpo_gzip)


@respx.mock
def test_executar_grava_resposta_original(session):
    respx.get(ibge.URL_MUNICIPIOS).respond(content=IBGE, headers=JSON)
    with httpx.Client() as client:
        coleta = executar(session, "ibge-municipios", ibge.coletar, client)
    assert coleta.status == "sucesso"
    r = session.scalars(select(RespostaBruta)).one()
    assert (r.coleta_id, r.fonte, r.metodo, r.status_http) == (
        coleta.id,
        "ibge-municipios",
        "GET",
        200,
    )
    assert r.url == ibge.URL_MUNICIPIOS
    assert r.sha256_original == r.sha256_gravado == hashlib.sha256(IBGE).hexdigest()
    assert r.tamanho_original == len(IBGE)
    assert r.redacao is None
    assert _corpo(session, r) == IBGE


@respx.mock
def test_conteudo_repetido_e_gravado_uma_vez(session):
    respx.get(ibge.URL_MUNICIPIOS).respond(content=IBGE, headers=JSON)
    with httpx.Client() as client:
        executar(session, "ibge-municipios", ibge.coletar, client)
        executar(session, "ibge-municipios", ibge.coletar, client)
    assert session.scalar(select(func.count()).select_from(RespostaBruta)) == 2
    assert session.scalar(select(func.count()).select_from(ConteudoBruto)) == 1


@respx.mock
def test_resposta_de_erro_fica_gravada_mesmo_com_falha_da_coleta(session):
    respx.get(ibge.URL_MUNICIPIOS).respond(status_code=503, content=b"Service Unavailable")
    with httpx.Client() as client:
        coleta = executar(session, "ibge-municipios", ibge.coletar, client)
    assert coleta.status == "falha"
    r = session.scalars(select(RespostaBruta)).one()
    assert (r.coleta_id, r.status_http) == (coleta.id, 503)
    assert _corpo(session, r) == b"Service Unavailable"


@respx.mock
def test_gravacao_so_vale_dentro_do_contexto(session):
    respx.get(ibge.URL_MUNICIPIOS).respond(content=IBGE, headers=JSON)
    with httpx.Client() as client:
        executar(session, "ibge-municipios", ibge.coletar, client)
        assert client.event_hooks["response"] == []
        get_json(client, ibge.URL_MUNICIPIOS)
    assert session.scalar(select(func.count()).select_from(RespostaBruta)) == 1


def _sem_cnpj(corpo: bytes) -> tuple[bytes, str]:
    dados = json.loads(corpo)
    for item in dados["items"]:
        item.pop("cnpj", None)
    return json.dumps(dados, ensure_ascii=False).encode(), "removido: items[].cnpj"


@respx.mock
def test_redator_grava_versao_sem_o_campo_e_guarda_hash_do_original(session):
    respx.get(siconfi.URL_ENTES).respond(content=ENTES, headers=JSON)
    coleta = Coleta(fonte="teste-redacao", status="executando")
    session.add(coleta)
    session.commit()
    with httpx.Client() as client, gravar_respostas(client, session, coleta):
        dados, rid = get_json(client, siconfi.URL_ENTES, redator=_sem_cnpj, com_origem=True)
    # o coletor recebe o dado completo; só o que é gravado passa pelo redator
    assert "cnpj" in dados["items"][0]
    r = session.get(RespostaBruta, rid)
    assert r.sha256_original == hashlib.sha256(ENTES).hexdigest()
    assert r.sha256_gravado != r.sha256_original
    assert r.redacao == "removido: items[].cnpj"
    gravado = _corpo(session, r)
    assert hashlib.sha256(gravado).hexdigest() == r.sha256_gravado
    assert all("cnpj" not in item for item in json.loads(gravado)["items"])


@respx.mock
def test_api_devolve_metadados_e_corpo(session):
    respx.get(ibge.URL_MUNICIPIOS).respond(content=IBGE, headers=JSON)
    with httpx.Client() as client:
        coleta = executar(session, "ibge-municipios", ibge.coletar, client)
    app.dependency_overrides[get_session] = lambda: session
    try:
        api = TestClient(app)
        lista = api.get(f"/api/coletas/{coleta.id}/respostas").json()
        assert lista["total"] == 1
        rid = lista["itens"][0]["id"]
        assert api.get(f"/api/respostas/{rid}").json()["url"] == ibge.URL_MUNICIPIOS
        corpo = api.get(f"/api/respostas/{rid}/corpo")
        assert corpo.content == IBGE
        assert corpo.headers["x-sha256-original"] == hashlib.sha256(IBGE).hexdigest()
        assert api.get("/api/respostas/999999").status_code == 404
    finally:
        app.dependency_overrides.clear()
