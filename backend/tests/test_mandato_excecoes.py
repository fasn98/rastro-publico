"""Linha do tempo do mandato (Câmara), exceções aprovadas de emendas e 2º turno pendente.

Amostras reais em tests/fixtures/politicos:
- camara_historico_220637.json: /deputados/220637/historico (Câmara, 06/10/2026);
- transparencia_emendas_herdadas.csv: 3 linhas do EmendasParlamentares.csv (06/10/2026);
- tse_consulta_cand_2026_DF_amostra.csv: linhas do consulta_cand_2026_DF.csv (gerado em
  05/10/2026), já sem as colunas pessoais.
"""

import csv
import datetime
import gzip
import io
import re
import zipfile

import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import FIXTURES
from rastro.api.main import app
from rastro.coletores.arquivo import ArquivoBruto
from rastro.coletores.base import novo_cliente
from rastro.db import get_session
from rastro.models import Municipio, PayloadBruto, RespostaBruta
from rastro.politicos import camara, transparencia, tse, vinculo
from rastro.politicos.modelos import PolEmenda, PolEventoMandato, PolPendencia, PolPolitico

POL = FIXTURES / "politicos"


@pytest.fixture
def cliente(engine):
    with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
        yield c


@pytest.fixture
def deputados(session, cliente):
    from test_politicos import _mock_camara

    with respx.mock:
        _mock_camara()
        return camara.coletar_deputados(session, cliente, "SP")


@pytest.fixture
def api(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


# ------------------------------------------------------------- exceções de emendas


def test_excecoes_emendas_tem_aprovacao_e_justificativa():
    excecoes = vinculo.carregar_excecoes()
    assert len(excecoes) == 2
    for e in excecoes:
        # o texto da fonte cita o ex-parlamentar de quem a emenda foi herdada
        ex = transparencia._normalizar(e["ex_parlamentar"])
        assert f"(EX-PARLAMENTAR {ex}," in transparencia._normalizar(e["texto_fonte"])
        assert e["rotulo"] == (
            f"Emenda herdada do ex-parlamentar {e['ex_parlamentar']}, "
            "nos termos do art. 78 da LDO 2025"
        )
        assert len(e["justificativa"]) > 100
        assert e["aprovado_por"] and isinstance(e["aprovado_em"], datetime.date)
        assert isinstance(e["camara_id"], int) and isinstance(e["ex_camara_id"], int)


@respx.mock
def test_emendas_herdadas_ligadas_ao_sucessor_com_rotulo(session, cliente, deputados):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        texto = (POL / "transparencia_emendas_herdadas.csv").read_text()
        z.writestr("EmendasParlamentares.csv", texto.replace("\n", "\r\n").encode("latin-1"))
    respx.get(transparencia.URL_ARQUIVO).respond(content=buf.getvalue())
    autores = {"JOAO CURY": vinculo.Autor(deputados[230957], "João Cury", 2024, 2027)}
    excecoes = vinculo.excecoes_por_texto(session)
    assert set(excecoes.values()) == {
        (
            deputados[230957],
            "Emenda herdada do ex-parlamentar Alberto Mourão, nos termos do art. 78 da LDO 2025",
        ),
        (
            deputados[175765],
            "Emenda herdada do ex-parlamentar Ricardo Silva, nos termos do art. 78 da LDO 2025",
        ),
    }
    r = transparencia.coletar_arquivo(session, cliente, "SP", 2023, autores, excecoes)
    assert (r["linhas"], r["ligadas"], r["por_excecao"]) == (3, 3, 2)
    assert r["codigo_de_autor_ambiguo"] == []  # o código do ex-parlamentar não desfaz o vínculo
    por_codigo = {e.codigo_emenda: e for e in session.scalars(select(PolEmenda))}
    herdada = por_codigo["202535970001"]
    assert (herdada.politico_id, herdada.vinculo, herdada.codigo_autor) == (
        deputados[230957],
        "excecao",
        "3597",
    )
    assert herdada.nome_autor.startswith("JOAO CURY NETO (EX-PARLAMENTAR ALBERTO MOURAO")
    assert "Alberto Mourão" in herdada.nota_vinculo
    assert por_codigo["202645510001"].vinculo == "nome"
    assert por_codigo["202542000001"].politico_id == deputados[175765]


# ------------------------------------------------------------- linha do tempo


@respx.mock
def test_linha_do_tempo_do_mandato_sem_email_no_arquivo_bruto(session, cliente, api):
    original = (POL / "camara_historico_220637.json").read_bytes()
    respx.get(f"{camara.API}/deputados/220637/historico").respond(
        content=original, headers={"content-type": "application/json"}
    )
    p = PolPolitico(
        fonte="camara",
        id_fonte="220637",
        nome="Marina Silva",
        cargo="deputado_federal",
        uf="SP",
        legislatura=57,
        url_fonte=f"{camara.API}/deputados/220637",
    )
    session.add(p)
    session.commit()
    assert camara.coletar_historico(session, cliente, 220637, p.id) == 4
    linha = api.get(f"/api/politicos/{p.id}").json()["linha_do_tempo"]
    assert [(x["inicio"][:10], x["situacao"], x["descricao_status"]) for x in linha] == [
        (
            "2023-02-01",
            "Exercício",
            "Entrada - Posse de Eleito Titular - Posse na Sessão Preparatória",
        ),
        ("2023-02-03", "Licença", "Saída - Afastamento sem prazo determinado - Ministro de Estado"),
        ("2026-04-01", "Exercício", "Entrada - Reassunção"),
    ]
    assert linha[0]["fim"][:10] == "2023-02-03" and linha[-1]["fim"] is None
    r = session.scalars(select(RespostaBruta).where(RespostaBruta.url.like("%historico"))).one()
    assert r.campos_removidos == ["email"]
    for pl in session.scalars(select(PayloadBruto)):
        assert not re.search(rb"[\w.+-]+@[\w-]+\.[\w.]+", gzip.decompress(pl.conteudo))
        assert b'"email"' not in gzip.decompress(pl.conteudo)
    assert session.query(PolEventoMandato).count() == 4


# ------------------------------------------------------------- 2026 e 2º turno


def _zip_2026_df() -> bytes:
    from test_tse import CABECALHO, _marcador

    linhas = list(
        csv.DictReader(
            io.StringIO((POL / "tse_consulta_cand_2026_DF_amostra.csv").read_text()),
            delimiter=";",
        )
    )
    saida = io.StringIO()
    w = csv.DictWriter(saida, CABECALHO, delimiter=";", quoting=csv.QUOTE_ALL)
    w.writeheader()
    for i, r in enumerate(linhas):
        w.writerow({**r, **{c: _marcador(c, i) for c in tse.COLUNAS_PESSOAIS}})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("consulta_cand_2026_DF.csv", saida.getvalue().encode("latin-1"))
    return buf.getvalue()


@respx.mock
def test_2026_cargo_com_segundo_turno_pendente_fica_oculto(session, cliente, api, monkeypatch):
    from rastro.config import get_settings

    session.add(Municipio(cod_ibge=5300108, nome="Brasília", uf="DF", regiao="CO"))
    session.commit()
    respx.get(tse.URL_CANDIDATOS.format(ano=2026)).respond(content=_zip_2026_df())
    r = tse.coletar_eleitos(session, cliente, 2026, "DF", set())
    assert r["eleitos"] == 2  # os 2 deputados federais; governador ainda sem eleito
    pend = session.scalars(select(PolPendencia).where(PolPendencia.cargo == "governador")).one()
    assert pend.tipo == "segundo_turno"
    assert pend.motivo == "2º turno pendente no arquivo do TSE: CELINA LEÃO, LEANDRO GRASS."
    monkeypatch.setenv("RASTRO_POL_PUBLICAR_TSE_2026", "1")
    get_settings.cache_clear()
    secoes = api.get("/api/municipios/5300108/representantes").json()["secoes"]
    [s26] = [s for s in secoes if "2026" in s["titulo"]]
    assert s26["titulo"] == (
        "Eleitos em 2026 por DF — resultado divulgado pelo TSE em 05/10/2026, "
        "mandato a partir de 2027, sujeito a alterações até a diplomação"
    )
    assert [g["cargo"] for g in s26["grupos"]] == ["deputado_federal"]
    assert "2º turno pendente" in s26["nota"]
