"""Auditoria: toda resposta das fontes é arquivada e todo valor aponta para a sua origem."""

import gzip
import hashlib
import json
from decimal import Decimal

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from conftest import FIXTURES, carregar
from rastro.api.main import app
from rastro.coletores import ibge
from rastro.coletores import siconfi_demonstrativos as sd
from rastro.coletores.arquivo import ArquivoBruto, coleta_atual, ler_payload
from rastro.coletores.base import executar, get_json, novo_cliente
from rastro.db import get_session
from rastro.models import (
    Coleta,
    ContaDemonstrativo,
    EnteSiconfi,
    Municipio,
    PayloadBruto,
    RespostaBruta,
)


@pytest.fixture
def cliente(engine):
    with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
        yield c


def _conta(session, modelo):
    return session.scalar(select(func.count()).select_from(modelo))


@respx.mock
def test_guarda_bytes_originais_url_e_sha256(session, cliente):
    bruto = (FIXTURES / "ibge_municipios.json").read_bytes()
    respx.get(ibge.URL_MUNICIPIOS).respond(
        content=bruto, headers={"content-type": "application/json;charset=UTF-8"}
    )
    get_json(cliente, ibge.URL_MUNICIPIOS, params={"view": "nivelado"})

    r = session.scalars(select(RespostaBruta)).one()
    assert r.url == ibge.URL_MUNICIPIOS + "?view=nivelado"  # URL completa, com parâmetros
    assert (r.metodo, r.status_http, r.tamanho) == ("GET", 200, len(bruto))
    assert r.content_type == "application/json;charset=UTF-8"
    assert r.sha256 == hashlib.sha256(bruto).hexdigest()  # hash dos bytes ORIGINAIS
    assert ler_payload(session.get(PayloadBruto, r.sha256)) == bruto


@respx.mock
def test_arquiva_tambem_erros_e_novas_tentativas(session, cliente, monkeypatch):
    monkeypatch.setenv("RASTRO_HTTP_TENTATIVAS", "3")
    from rastro.config import get_settings

    get_settings.cache_clear()
    respx.get(ibge.URL_MUNICIPIOS).side_effect = [
        httpx.Response(503, text="indisponível"),
        httpx.Response(200, json=[]),
    ]
    get_json(cliente, ibge.URL_MUNICIPIOS)
    status = session.scalars(select(RespostaBruta.status_http).order_by(RespostaBruta.id)).all()
    assert status == [503, 200]


@respx.mock
def test_conteudo_igual_e_guardado_uma_vez(session, cliente):
    respx.get(ibge.URL_MUNICIPIOS).respond(json=[{"id": 1}])
    get_json(cliente, ibge.URL_MUNICIPIOS)
    get_json(cliente, ibge.URL_MUNICIPIOS)
    assert _conta(session, RespostaBruta) == 2
    assert _conta(session, PayloadBruto) == 1


@respx.mock
def test_resposta_fica_ligada_a_coleta_mesmo_se_ela_falhar(session, cliente):
    respx.get(ibge.URL_MUNICIPIOS).respond(json={"formato": "inesperado"})
    coleta = executar(session, "ibge-municipios", ibge.coletar, cliente)
    assert coleta.status == "falha"
    r = session.scalars(select(RespostaBruta)).one()  # o rollback da coleta não apagou
    assert r.coleta_id == coleta.id
    assert coleta_atual.get() is None


@respx.mock
def test_municipio_aponta_para_a_resposta(session, cliente):
    respx.get(ibge.URL_MUNICIPIOS).respond(json=carregar("ibge_municipios.json"))
    ibge.coletar(session, cliente)
    origem = session.scalars(select(Municipio.resposta_id).distinct()).one()
    assert origem == session.scalars(select(RespostaBruta.id)).one()


@respx.mock
def test_cada_valor_do_demonstrativo_aponta_para_a_pagina_de_origem(
    session, cliente, monkeypatch, mapeamento_total
):
    """RREO em duas páginas: cada linha aponta para a página exata de onde veio."""
    from rastro.config import get_settings

    monkeypatch.setenv("RASTRO_SICONFI_ITENS_POR_PAGINA", "50")
    get_settings.cache_clear()
    rreo = carregar("adamantina_2025_rreo6.json")["items"]
    pagina1 = {"items": rreo[:50], "hasMore": True}
    pagina2 = {"items": rreo[50:], "hasMore": False}
    respx.get(sd.URL_EXTRATO).respond(json=carregar("siconfi_extrato_adamantina_2025.json"))
    respx.get(sd.URL_RREO, params__contains={"offset": "0"}).respond(json=pagina1)
    respx.get(sd.URL_RREO, params__contains={"offset": "50"}).respond(json=pagina2)
    respx.get(sd.URL_RGF).respond(json={"items": [], "hasMore": False})
    ente = EnteSiconfi(cod_ibge=3500105, nome="Adamantina", esfera="M", uf="SP")

    sd.coletar_ente(session, cliente, ente, 2025)

    linhas = session.execute(
        select(ContaDemonstrativo.valor, RespostaBruta.url)
        .join(RespostaBruta, RespostaBruta.id == ContaDemonstrativo.resposta_id)
        .order_by(ContaDemonstrativo.id)
    ).all()
    assert linhas and all(url for _, url in linhas)  # nenhum valor sem origem
    urls = {url for _, url in linhas}
    assert any("offset=0" in u for u in urls) and any("offset=50" in u for u in urls)

    # TODA linha gravada está, com o mesmo valor, na página para a qual aponta
    gravadas = session.scalars(select(ContaDemonstrativo)).all()
    paginas = {}
    for c in gravadas:
        if c.resposta_id not in paginas:
            r = session.get(RespostaBruta, c.resposta_id)
            bruto = ler_payload(session.get(PayloadBruto, r.sha256))
            paginas[c.resposta_id] = json.loads(bruto, parse_float=Decimal)["items"]
        chave = (c.anexo, c.rotulo, c.cod_conta, c.conta, c.coluna, c.valor)
        assert chave in {
            (i["anexo"], i["rotulo"], i["cod_conta"], i["conta"], i["coluna"], i["valor"])
            for i in paginas[c.resposta_id]
        }


@respx.mock
def test_api_devolve_bytes_originais_e_detecta_corrupcao(session, cliente):
    bruto = (FIXTURES / "ibge_municipios.json").read_bytes()
    respx.get(ibge.URL_MUNICIPIOS).respond(
        content=bruto, headers={"content-type": "application/json"}
    )
    get_json(cliente, ibge.URL_MUNICIPIOS)
    rid = session.scalars(select(RespostaBruta.id)).one()

    app.dependency_overrides[get_session] = lambda: session
    try:
        api = TestClient(app)
        r = api.get(f"/api/respostas/{rid}/bruto")
        assert r.content == bruto
        assert r.headers["x-rastro-sha256"] == hashlib.sha256(bruto).hexdigest()
        assert api.get(f"/api/respostas/{rid}").json()["integra"] is True

        p = session.scalars(select(PayloadBruto)).one()
        p.conteudo = gzip.compress(b"adulterado")
        session.commit()
        assert api.get(f"/api/respostas/{rid}").json()["integra"] is False
        assert api.get(f"/api/respostas/{rid}/bruto").status_code == 500
    finally:
        app.dependency_overrides.clear()


def test_coleta_registrada_no_modelo():
    # garante que a ligação resposta -> coleta existe no esquema
    assert RespostaBruta.__table__.c.coleta_id.references(Coleta.__table__.c.id)
