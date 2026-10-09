"""Módulo de políticos: coletores e API, com respostas reais gravadas (tests/fixtures/politicos).

As amostras dos arquivos CSV da Câmara são trechos fiéis (linhas inteiras, sem alteração)
dos arquivos oficiais de 2025, baixados em 06/10/2026.
"""

import csv
import io
import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select

from conftest import FIXTURES, carregar
from rastro.api.main import app
from rastro.coletores import ibge
from rastro.coletores.arquivo import ArquivoBruto
from rastro.coletores.base import executar, novo_cliente
from rastro.db import get_session
from rastro.models import Municipio
from rastro.politicos import camara, coletar, senado, transparencia
from rastro.politicos.modelos import (
    PolComissao,
    PolEmenda,
    PolPolitico,
    PolPresenca,
    PolProposicao,
    PolVotacao,
)

POL = FIXTURES / "politicos"
JSON = {"content-type": "application/json"}
CSV = {"content-type": "text/csv"}


def _json(nome):
    return (POL / nome).read_bytes()


def _csv(nome):
    texto = (POL / nome).read_bytes().decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(texto), delimiter=";"))


def _conta(session, modelo):
    return session.scalar(select(func.count()).select_from(modelo))


def _deputados(request: httpx.Request) -> httpx.Response:
    p = request.url.params
    if "idLegislatura" not in p:
        return httpx.Response(200, content=_json("camara_deputados_sp_atual.json"), headers=JSON)
    pagina = "p2" if p.get("pagina") == "2" else "p1"
    return httpx.Response(
        200, content=_json(f"camara_deputados_sp_leg57_{pagina}.json"), headers=JSON
    )


def _mock_camara():
    respx.get(f"{camara.API}/deputados").mock(side_effect=_deputados)
    respx.get(f"{camara.API}/proposicoes").respond(
        content=_json("camara_proposicoes_204534_2025_p1.json"), headers=JSON
    )
    a = camara.ARQUIVOS
    respx.get(f"{a}/votacoes/csv/votacoes-2025.csv").respond(
        content=_json("camara_votacoes_2025_amostra.csv"), headers=CSV
    )
    respx.get(f"{a}/votacoesVotos/csv/votacoesVotos-2025.csv").respond(
        content=_json("camara_votacoesVotos_2025_amostra.csv"), headers=CSV
    )
    respx.get(f"{a}/eventosPresencaDeputados/csv/eventosPresencaDeputados-2025.csv").respond(
        content=_json("camara_eventosPresencaDeputados_2025_amostra.csv"), headers=CSV
    )


def _mock_senado():
    s = senado.API
    respx.get(f"{s}/senador/lista/atual.json").respond(
        content=_json("senado_senadores_atual.json"), headers=JSON
    )
    respx.get(f"{s}/processo").respond(
        content=_json("senado_processo_6009_2025_amostra.json"), headers=JSON
    )
    respx.get(f"{s}/votacao").respond(
        content=_json("senado_votacao_6009_2025_amostra.json"), headers=JSON
    )
    respx.get(url__regex=rf"{s}/senador/\d+/comissoes\.json").respond(
        content=_json("senado_comissoes_6009.json"), headers=JSON
    )


# ---------------------------------------------------------------- LGPD


def test_tabelas_nao_tem_colunas_de_dados_pessoais(engine):
    proibidas = {"cpf", "data_nascimento", "nascimento", "endereco", "email", "titulo_eleitoral"}
    for tabela in inspect(engine).get_table_names():
        if tabela.startswith("pol_"):
            colunas = {c["name"] for c in inspect(engine).get_columns(tabela)}
            assert not colunas & proibidas, tabela


@respx.mock
def test_coletores_nao_chamam_detalhes_com_dados_pessoais(session):
    # /deputados/{id} (CPF, nascimento) e /senador/{codigo} (nascimento, endereço)
    detalhe_dep = respx.get(url__regex=rf"{camara.API}/deputados/\d+$")
    detalhe_sen = respx.get(url__regex=rf"{senado.API}/senador/\d+(\.json)?$")
    _mock_camara()
    _mock_senado()
    with httpx.Client() as client:
        camara.coletar_deputados(session, client, "SP")
        senado.coletar_senadores(session, client, "SP")
    assert not detalhe_dep.called and not detalhe_sen.called


# ---------------------------------------------------------------- Câmara


@respx.mock
def test_camara_deputados_da_legislatura_e_em_exercicio(session):
    _mock_camara()
    with httpx.Client() as client:
        mapa = camara.coletar_deputados(session, client, "SP")
    leg = [
        d
        for f in ("camara_deputados_sp_leg57_p1.json", "camara_deputados_sp_leg57_p2.json")
        for d in carregar(f"politicos/{f}")["dados"]
    ]
    atuais = {d["id"] for d in carregar("politicos/camara_deputados_sp_atual.json")["dados"]}
    assert set(mapa) == {d["id"] for d in leg}
    assert _conta(session, PolPolitico) == len(mapa)
    em_exercicio = session.scalar(
        select(func.count()).select_from(PolPolitico).where(PolPolitico.em_exercicio.is_(True))
    )
    assert em_exercicio == len(atuais) == 70
    p = session.get(PolPolitico, mapa[204534])
    assert (p.nome, p.partido, p.uf, p.cargo, p.legislatura) == (
        "Tabata Amaral",
        "PSB",
        "SP",
        "deputado_federal",
        57,
    )
    assert p.url_fonte == "https://dadosabertos.camara.leg.br/api/v2/deputados/204534"
    # a lista da legislatura traz Carlos Sampaio duas vezes (PSDB e PSD); vale a atual
    assert session.get(PolPolitico, mapa[74262]).partido == "PSD"
    fora = [d for d in leg if d["id"] not in atuais]
    partidos = {d["siglaPartido"] for d in leg if d["id"] == fora[0]["id"]}
    assert set(session.get(PolPolitico, mapa[fora[0]["id"]]).partido.split(" / ")) == partidos


@respx.mock
def test_camara_proposicoes(session):
    _mock_camara()
    with httpx.Client() as client:
        mapa = camara.coletar_deputados(session, client, "SP")
        n = camara.coletar_proposicoes(session, client, 204534, mapa[204534], 2025)
    assert n == len(carregar("politicos/camara_proposicoes_204534_2025_p1.json")["dados"]) == 85
    pec = session.scalars(select(PolProposicao).where(PolProposicao.id_fonte == "2485341")).one()
    assert (pec.sigla_tipo, pec.numero, pec.ano, str(pec.data_apresentacao)) == (
        "PEC",
        "8",
        2025,
        "2025-02-25",
    )
    assert pec.url_pagina == "https://www.camara.leg.br/propostas-legislativas/2485341"


@respx.mock
def test_camara_votos_so_dos_deputados_da_uf(session):
    _mock_camara()
    with httpx.Client() as client:
        mapa = camara.coletar_deputados(session, client, "SP")
        n = camara.coletar_votos(session, client, 2025, mapa)
    votos = _csv("camara_votacoesVotos_2025_amostra.csv")
    esperados = [v for v in votos if int(v["deputado_id"]) in mapa]
    assert 0 < n == len(esperados) < len(votos)
    v = esperados[0]
    gravado = session.scalars(
        select(PolVotacao).where(
            PolVotacao.politico_id == mapa[int(v["deputado_id"])],
            PolVotacao.id_votacao == v["idVotacao"],
        )
    ).one()
    sobre = {x["id"]: x for x in _csv("camara_votacoes_2025_amostra.csv")}[v["idVotacao"]]
    assert gravado.voto == v["voto"]
    assert str(gravado.data) == sobre["data"]
    assert gravado.orgao == sobre["siglaOrgao"]
    assert gravado.url_fonte == v["uriVotacao"]


@respx.mock
def test_camara_presencas(session):
    _mock_camara()
    with httpx.Client() as client:
        mapa = camara.coletar_deputados(session, client, "SP")
        n = camara.coletar_presencas(session, client, 2025, mapa)
    linhas = _csv("camara_eventosPresencaDeputados_2025_amostra.csv")
    assert n == sum(1 for p in linhas if int(p["idDeputado"]) in mapa)
    eventos = {p["idEvento"] for p in linhas if p["idDeputado"] == "204534"}
    gravados = session.scalars(
        select(PolPresenca.id_evento).where(PolPresenca.politico_id == mapa[204534])
    ).all()
    assert set(gravados) == eventos == {"75098", "75320"}


# ---------------------------------------------------------------- Senado


@respx.mock
def test_senado_senadores_da_uf(session):
    _mock_senado()
    with httpx.Client() as client:
        mapa = senado.coletar_senadores(session, client, "SP")
    assert set(mapa) == {"6009", "6008", "5376"}
    p = session.get(PolPolitico, mapa["6009"])
    assert (p.nome, p.partido, p.situacao) == ("Astronauta Marcos Pontes", "PL", "Titular")
    assert (str(p.mandato_inicio), str(p.mandato_fim)) == ("2023-02-01", "2031-01-31")
    suplente = session.get(PolPolitico, mapa["6008"])
    assert (suplente.nome, suplente.situacao) == ("Giordano", "1º Suplente")


@respx.mock
def test_senado_materias_votacoes_e_comissoes(session):
    _mock_senado()
    with httpx.Client() as client:
        pid = senado.coletar_senadores(session, client, "SP")["6009"]
        assert senado.coletar_materias(session, client, "6009", pid, 2025) == 8
        assert senado.coletar_votacoes(session, client, "6009", pid, 2025) == 8
        assert senado.coletar_comissoes(session, client, "6009", pid) == 61
    rqs = session.scalars(select(PolProposicao).where(PolProposicao.id_fonte == "8787873")).one()
    assert (rqs.sigla_tipo, rqs.numero, rqs.ano) == ("RQS", "36", 2025)
    assert "Astronauta Marcos Pontes (PL/SP)" in rqs.autoria
    ap = session.scalars(select(PolVotacao).where(PolVotacao.voto == "AP")).one()
    assert (ap.materia, str(ap.data), ap.voto_descricao) == (
        "PLP 22/2025",
        "2025-02-19",
        "Atividade parlamentar",
    )
    car = session.scalars(select(PolComissao).where(PolComissao.sigla == "CAR")).one()
    assert (str(car.data_inicio), str(car.data_fim)) == ("2024-11-28", "2025-03-25")


# ---------------------------------------------------------------- Emendas


@respx.mock
def test_emendas_401_real_falha_com_aviso_e_nao_grava_nada(session, monkeypatch):
    # resposta real da API sem chave (gravada em 06/10/2026): sem variável e sem proxy
    monkeypatch.delenv(transparencia.VARIAVEL_CHAVE, raising=False)
    _mock_senado()
    rota = respx.get(f"{transparencia.API}/emendas").respond(
        401,
        content=_json("transparencia_emendas_sem_chave.json"),
        headers={"content-type": "application/json;charset=ISO-8859-1"},
    )
    with httpx.Client() as client:
        senado.coletar_senadores(session, client, "SP")
        assert "proxy" in transparencia.preparar_cliente(client)
        coleta = executar(session, "pol-emendas", coletar.coletor_emendas("SP", [2025]), client)
    assert coleta.status == "falha"
    assert "401" in coleta.erro and "proxy" in coleta.erro
    assert rota.call_count == 1  # só a consulta de teste; nenhum autor consultado
    assert "chave-api-dados" not in rota.calls[0].request.headers
    assert _conta(session, PolEmenda) == 0


@pytest.mark.parametrize("com_variavel", [True, False])
def test_emendas_modos_de_chave(monkeypatch, com_variavel):
    """Com a variável, o cabeçalho é enviado; sem ela, nada é enviado (o proxy injeta)."""
    if com_variavel:
        monkeypatch.setenv(transparencia.VARIAVEL_CHAVE, "valor-de-teste")
    else:
        monkeypatch.delenv(transparencia.VARIAVEL_CHAVE, raising=False)
    with httpx.Client() as client:
        modo = transparencia.preparar_cliente(client)
        enviado = client.headers.get("chave-api-dados")
    assert (enviado == "valor-de-teste") is com_variavel
    assert (enviado is None) is not com_variavel
    assert ("proxy" in modo) is not com_variavel


# ---------------------------------------------------------------- API


@pytest.fixture
def api(session, engine):
    respx_mock = respx.mock(assert_all_called=False)
    with respx_mock:
        respx_mock.get(ibge.URL_MUNICIPIOS).respond(
            content=(FIXTURES / "ibge_municipios.json").read_bytes(), headers=JSON
        )
        respx_mock.route(
            host="dadosabertos.camara.leg.br", path__startswith="/api/v2/deputados"
        ).mock(side_effect=_deputados)
        s = senado.API
        for caminho, nome in (
            ("/senador/lista/atual.json", "senado_senadores_atual.json"),
            ("/processo", "senado_processo_6009_2025_amostra.json"),
            ("/votacao", "senado_votacao_6009_2025_amostra.json"),
            ("/senador/6009/comissoes.json", "senado_comissoes_6009.json"),
        ):
            respx_mock.get(f"{s}{caminho}").respond(content=_json(nome), headers=JSON)
        with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as client:
            executar(session, "ibge-municipios", ibge.coletar, client)
            camara.coletar_deputados(session, client, "SP")
            pid = senado.coletar_senadores(session, client, "SP")["6009"]
            senado.coletar_materias(session, client, "6009", pid, 2025)
            senado.coletar_votacoes(session, client, "6009", pid, 2025)
            senado.coletar_comissoes(session, client, "6009", pid)
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app), pid
    app.dependency_overrides.clear()


def test_api_lista_em_ordem_alfabetica(api):
    client, _ = api
    r = client.get("/api/politicos", params={"uf": "SP", "cargo": "senador"}).json()
    assert [p["nome"] for p in r["itens"]] == [
        "Astronauta Marcos Pontes",
        "Giordano",
        "Mara Gabrilli",
    ]
    deps = client.get("/api/politicos", params={"cargo": "deputado_federal", "limite": 500}).json()
    nomes = [p["nome"] for p in deps["itens"]]
    assert deps["total"] == len(nomes) == 90  # deputados distintos na legislatura 57
    assert nomes[0] == "Adilson Barroso"


def test_api_representantes_do_municipio(api, session):
    client, _ = api
    r = client.get("/api/municipios/3550308/representantes").json()
    assert r["municipio"] == {"cod_ibge": 3550308, "nome": "São Paulo", "uf": "SP"}
    titulos = [sec["titulo"] for sec in r["secoes"]]
    assert titulos == [
        "Eleitos em São Paulo",
        "Governador e deputados estaduais eleitos por SP — representam todo o estado",
        "Senadores e deputados federais eleitos por SP — representam todo o estado",
    ]
    grupos = {g["cargo"]: g for sec in r["secoes"] for g in sec["grupos"]}
    assert list(grupos) == [
        "prefeito",
        "vereador",
        "governador",
        "deputado_estadual",
        "senador",
        "deputado_federal",
    ]
    assert len(grupos["senador"]["politicos"]) == 3
    assert len(grupos["deputado_federal"]["politicos"]) == 70  # só os em exercício
    for cargo in ("prefeito", "vereador", "governador", "deputado_estadual"):
        assert grupos[cargo]["politicos"] == [] and "TSE" in grupos[cargo]["pendente"]
    assert client.get("/api/municipios/1/representantes").status_code == 404


def test_api_detalhe_com_contagens_e_fontes(api):
    client, pid = api
    r = client.get(f"/api/politicos/{pid}").json()
    assert r["nome"] == "Astronauta Marcos Pontes"
    assert r["fonte_registro"]["url"] == f"{senado.API}/senador/lista/atual.json"
    [prop] = r["proposicoes"]
    assert (prop["ano"], prop["quantidade"]) == (2025, 8)
    assert prop["fontes"][0]["url"] == (
        f"{senado.API}/processo?codigoParlamentarAutor=6009&ano=2025"
    )
    [vot] = r["votacoes"]
    assert vot["quantidade"] == 8
    assert vot["por_voto"] == {
        "AP": 1,
        "Abstenção": 1,
        "LS": 1,
        "MIS": 1,
        "Não": 1,
        "P-NRV": 1,
        "Sim": 1,
        "Votou": 1,
    }
    assert r["descricao_votos"]["AP"] == "Atividade parlamentar"
    assert "Sim" not in r["descricao_votos"]  # a fonte não descreve votos comuns
    assert len(r["comissoes"]) == 61
    texto = json.dumps(r)
    for campo in ("DataNascimento", "cpf", "EnderecoParlamentar", "NomeCompletoParlamentar"):
        assert campo not in texto


def test_api_listas_por_ano_e_emendas_sem_coleta(api):
    client, pid = api
    assert client.get(f"/api/politicos/{pid}/votacoes", params={"ano": 2025}).json()["total"] == 8
    assert client.get(f"/api/politicos/{pid}/votacoes", params={"ano": 2024}).json()["total"] == 0
    props = client.get(f"/api/politicos/{pid}/proposicoes", params={"ano": 2025}).json()
    assert props["total"] == 8 and all(p["resposta_id"] for p in props["itens"])
    e = client.get(f"/api/politicos/{pid}/emendas").json()
    assert e["coletadas"] is False and e["itens"] == [] and "não coletadas" in e["aviso"]
    assert client.get("/api/politicos/999999").status_code == 404
    assert client.get("/api/municipios/3550308/emendas").json()["coletadas"] is False


def test_coleta_registra_municipio_na_tabela_ibge(api, session):
    # pré-condição dos testes de representantes: o município existe na base do IBGE
    assert session.get(Municipio, 3550308).nome == "São Paulo"


@respx.mock
def test_coleta_de_emendas_envia_a_chave_em_toda_consulta(session, monkeypatch):
    """T-005: pelo caminho da coleta (`rastro politicos --fontes emendas-api`), a consulta
    chega à API com o cabeçalho `chave-api-dados`. Antes, a chave ia para um cliente
    descartado e a API respondia "Chave de API não informada"."""
    from contextlib import nullcontext

    monkeypatch.setenv(transparencia.VARIAVEL_CHAVE, " valor-de-teste\n")  # com espaços
    # sem arquivo bruto nem banco de produção: o cliente-base é um httpx.Client simples
    monkeypatch.setattr(coletar, "novo_cliente", lambda: httpx.Client())
    monkeypatch.setattr(coletar, "get_sessionmaker", lambda: lambda: nullcontext(session))
    # resposta real da API (gravada em 06/10/2026); aqui importa o que foi ENVIADO
    rota = respx.get(f"{transparencia.API}/emendas").respond(
        401,
        content=_json("transparencia_emendas_sem_chave.json"),
        headers={"content-type": "application/json;charset=ISO-8859-1"},
    )
    assert coletar.main(["--uf", "SP", "--anos", "2025", "--fontes", "emendas-api"]) == 1
    assert rota.call_count >= 1
    for chamada in rota.calls:
        assert chamada.request.headers["chave-api-dados"] == "valor-de-teste"
        # a chave vai no cabeçalho, nunca na URL (que é o que o arquivo bruto guarda)
        assert "valor-de-teste" not in str(chamada.request.url)


def test_so_as_emendas_recebem_a_chave(monkeypatch):
    monkeypatch.setenv(transparencia.VARIAVEL_CHAVE, "valor-de-teste")
    for fonte in ("camara", "senado", "emendas", "tse"):
        with coletar.cliente_da_fonte(fonte, base=httpx.Client)() as client:
            assert "chave-api-dados" not in client.headers
    with coletar.cliente_da_fonte("emendas-api", base=httpx.Client)() as client:
        assert client.headers["chave-api-dados"] == "valor-de-teste"
