"""TSE: eleitos de 2024 e 2022, redação LGPD e cruzamento TSE <-> IBGE.

As amostras em tests/fixtures/politicos/tse_* são linhas reais dos arquivos do TSE
(consulta_cand_2024/2022, baixados em 06/10/2026), já SEM as colunas pessoais: nenhum
dado pessoal real fica no repositório. Para testar a redação, o teste remonta o arquivo no
layout original (50 colunas, Latin-1, dentro de ZIP) preenchendo as 17 colunas pessoais
com MARCADORES DE TESTE, e confere que nenhum marcador chega ao banco nem ao arquivo bruto.
"""

import csv
import gzip
import io
import re
import zipfile

import pytest
import respx
from sqlalchemy import func, select, text

from conftest import FIXTURES
from rastro.coletores.arquivo import ArquivoBruto, sha256
from rastro.coletores.base import novo_cliente
from rastro.models import PayloadBruto, RespostaBruta
from rastro.politicos import tse
from rastro.politicos.modelos import PolPendencia, PolPolitico

POL = FIXTURES / "politicos"


def _trava(monkeypatch, nome: str, valor: str) -> None:
    """Liga/desliga uma trava de publicação (Settings) durante o teste."""
    from rastro.config import get_settings

    monkeypatch.setenv(nome, valor)
    get_settings.cache_clear()


# cabeçalho real do consulta_cand_2024_SP.csv (e de 2022), na ordem original
CABECALHO = (
    "DT_GERACAO;HH_GERACAO;ANO_ELEICAO;CD_TIPO_ELEICAO;NM_TIPO_ELEICAO;NR_TURNO;CD_ELEICAO;"
    "DS_ELEICAO;DT_ELEICAO;TP_ABRANGENCIA;SG_UF;SG_UE;NM_UE;CD_CARGO;DS_CARGO;SQ_CANDIDATO;"
    "NR_CANDIDATO;NM_CANDIDATO;NM_URNA_CANDIDATO;NM_SOCIAL_CANDIDATO;NR_CPF_CANDIDATO;DS_EMAIL;"
    "CD_SITUACAO_CANDIDATURA;DS_SITUACAO_CANDIDATURA;TP_AGREMIACAO;NR_PARTIDO;SG_PARTIDO;"
    "NM_PARTIDO;NR_FEDERACAO;NM_FEDERACAO;SG_FEDERACAO;DS_COMPOSICAO_FEDERACAO;SQ_COLIGACAO;"
    "NM_COLIGACAO;DS_COMPOSICAO_COLIGACAO;SG_UF_NASCIMENTO;DT_NASCIMENTO;"
    "NR_TITULO_ELEITORAL_CANDIDATO;CD_GENERO;DS_GENERO;CD_GRAU_INSTRUCAO;DS_GRAU_INSTRUCAO;"
    "CD_ESTADO_CIVIL;DS_ESTADO_CIVIL;CD_COR_RACA;DS_COR_RACA;CD_OCUPACAO;DS_OCUPACAO;"
    "CD_SIT_TOT_TURNO;DS_SIT_TOT_TURNO"
).split(";")


def _marcador(coluna: str, i: int) -> str:
    if coluna == "DS_EMAIL":
        return f"marcador.{i}@exemplo.invalid"
    return f"MARCADOR-TESTE-{coluna}-{i}"


def _zip_original(ano: int) -> bytes:
    """Remonta o ZIP no layout do TSE a partir da amostra real redigida + marcadores."""
    linhas = list(
        csv.DictReader(
            io.StringIO((POL / f"tse_consulta_cand_{ano}_SP_amostra.csv").read_text()),
            delimiter=";",
        )
    )
    saida = io.StringIO()
    w = csv.DictWriter(
        saida, CABECALHO, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n"
    )
    w.writeheader()
    for i, r in enumerate(linhas):
        w.writerow({**r, **{c: _marcador(c, i) for c in tse.COLUNAS_PESSOAIS}})
    conteudo = saida.getvalue().encode("latin-1")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("leiame.pdf", b"")
        z.writestr(f"consulta_cand_{ano}_SP.csv", conteudo)
        z.writestr(f"consulta_cand_{ano}_BRASIL.csv", conteudo)
    return buf.getvalue()


def _zip_municipios(linhas_extra: str = "") -> bytes:
    texto = (POL / "tse_municipio_tse_ibge_SP.csv").read_text() + linhas_extra
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("municipio_tse_ibge.csv", texto.encode("latin-1"))
    return buf.getvalue()


# Adamantina, Eldorado, Martinópolis, Sarutaiá
AMOSTRA_IBGE = {3500105, 3514809, 3529203, 3551207}


@pytest.fixture
def cliente(engine):
    with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
        yield c


def _mock(zip24=None, zip22=None, municipios=None):
    respx.get(tse.URL_MUNICIPIOS).respond(content=municipios or _zip_municipios())
    respx.get(tse.URL_CANDIDATOS.format(ano=2024)).respond(content=zip24 or _zip_original(2024))
    respx.get(tse.URL_CANDIDATOS.format(ano=2022)).respond(content=zip22 or _zip_original(2022))


def test_codigos_da_amostra_conferem_com_a_tabela_oficial():
    tabela = {
        int(r["CD_MUNICIPIO_IBGE"]): r["NM_MUNICIPIO_TSE"]
        for r in csv.DictReader(
            io.StringIO((POL / "tse_municipio_tse_ibge_SP.csv").read_text()), delimiter=";"
        )
    }
    assert len(tabela) == 645
    assert {tabela[c] for c in AMOSTRA_IBGE} == {
        "Adamantina",
        "Eldorado",
        "Martinópolis",
        "Sarutaiá",
    }


@respx.mock
def test_eleitos_2024_com_suplementar_e_pendencias(session, cliente):
    _mock()
    r = tse.coletar_eleitos(session, cliente, 2024, "SP", AMOSTRA_IBGE)
    assert r["unidades"] == 4
    prefeitos = {
        p.cod_ibge: p
        for p in session.scalars(select(PolPolitico).where(PolPolitico.cargo == "prefeito"))
    }
    assert set(prefeitos) == {3500105, 3514809}
    assert (prefeitos[3500105].nome, prefeitos[3500105].partido) == ("JOSÉ TIVERON", "NOVO")
    eld = prefeitos[3514809]  # eleição ordinária sem eleito; vale a suplementar
    assert (eld.nome, eld.situacao) == (
        "PROF. NOEL CASTELO",
        "ELEITO (Eleição Suplementar de Eldorado, 06/04/2025)",
    )
    pend = {
        p.cod_ibge: p.motivo
        for p in session.scalars(select(PolPendencia).where(PolPendencia.cargo == "prefeito"))
    }
    assert pend[3529203].endswith(
        "Suplementar de Martinópolis - out/26 marcada para 25/10/2026, "
        "ainda sem resultado no arquivo."
    )
    assert pend[3551207] == "Não consta prefeito eleito no arquivo do TSE."
    # vereadores: exatamente os ELEITO / POR QP / POR MÉDIA da amostra, por município
    amostra = list(
        csv.DictReader(
            io.StringIO((POL / "tse_consulta_cand_2024_SP_amostra.csv").read_text()),
            delimiter=";",
        )
    )
    esperado = sum(
        1 for x in amostra if x["DS_CARGO"] == "VEREADOR" and x["DS_SIT_TOT_TURNO"] in tse.ELEITO
    )
    vereadores = session.scalar(
        select(func.count()).select_from(PolPolitico).where(PolPolitico.cargo == "vereador")
    )
    assert vereadores == esperado > 0


@respx.mock
def test_eleitos_2022_governador_no_segundo_turno(session, cliente):
    _mock()
    tse.coletar_eleitos(session, cliente, 2022, "SP", set())
    gov = session.scalars(select(PolPolitico).where(PolPolitico.cargo == "governador")).one()
    assert (gov.nome, gov.partido, gov.situacao) == (
        "TARCÍSIO",
        "REPUBLICANOS",
        "ELEITO (2º turno)",
    )
    assert gov.cod_ibge is None and gov.eleicao_ano == 2022
    assert (
        session.scalar(
            select(func.count())
            .select_from(PolPolitico)
            .where(PolPolitico.cargo == "deputado_estadual")
        )
        == 2
    )


@respx.mock
def test_arquivo_bruto_sem_dados_pessoais_e_com_hash_do_original(session, cliente):
    zip24 = _zip_original(2024)
    _mock(zip24=zip24)
    tse.coletar_eleitos(session, cliente, 2024, "SP", AMOSTRA_IBGE)
    r = session.scalars(
        select(RespostaBruta).where(RespostaBruta.url == tse.URL_CANDIDATOS.format(ano=2024))
    ).one()
    assert r.sha256_original == sha256(zip24) and r.tamanho_original == len(zip24)
    assert r.campos_removidos == list(tse.COLUNAS_PESSOAIS)
    assert "membro consulta_cand_2024_SP.csv" in r.redacao
    # em nenhum lugar do banco (tabelas e payloads) há marcador de dado pessoal
    tudo = [
        linha.encode()
        for t in session.execute(
            text("select tablename from pg_tables where schemaname = 'public'")
        ).scalars()
        for linha in session.execute(text(f'select row_to_json(x)::text from "{t}" x')).scalars()
    ] + [gzip.decompress(p.conteudo) for p in session.scalars(select(PayloadBruto))]
    for conteudo in tudo:
        assert b"MARCADOR-TESTE" not in conteudo
        assert not re.search(rb"[\w.+-]+@[\w-]+\.[\w.]+", conteudo)


@respx.mock
def test_cruzamento_sem_par_unico_falha_sem_gravar(session, cliente):
    # uma linha a mais ligando um código TSE de SP a um segundo código IBGE
    extra = '"04/10/2026";"09:00:06";31;35;"SP";"São Paulo";"61018";"Adamantina";9999999;"X"\n'
    _mock(municipios=_zip_municipios(extra))
    with pytest.raises(tse.CruzamentoIncompleto, match="61018"):
        tse.coletar_eleitos(session, cliente, 2024, "SP", AMOSTRA_IBGE)
    session.rollback()
    assert session.scalar(select(func.count()).select_from(PolPolitico)) == 0


@respx.mock
def test_municipio_ibge_sem_par_falha(session, cliente):
    _mock()
    with pytest.raises(tse.CruzamentoIncompleto, match="sem par"):
        tse.coletar_eleitos(session, cliente, 2024, "SP", AMOSTRA_IBGE | {1234567})


@respx.mock
def test_representantes_so_mostram_tse_com_a_trava_ligada(session, cliente, monkeypatch):
    from fastapi.testclient import TestClient

    from rastro.api.main import app
    from rastro.db import get_session
    from rastro.models import Municipio

    session.add(Municipio(cod_ibge=3500105, nome="Adamantina", uf="SP", regiao="SE"))
    session.commit()
    _mock()
    tse.coletar_eleitos(session, cliente, 2024, "SP", AMOSTRA_IBGE)
    app.dependency_overrides[get_session] = lambda: session
    try:
        api = TestClient(app)

        def prefeito():
            r = api.get("/api/municipios/3500105/representantes").json()
            [g] = [g for s in r["secoes"] for g in s["grupos"] if g["cargo"] == "prefeito"]
            return g

        _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE", "0")
        g = prefeito()
        assert g["politicos"] == [] and "TSE" in g["pendente"]
        assert api.get("/api/politicos", params={"cargo": "vereador"}).json()["total"] == 0
        _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE", "1")
        g = prefeito()
        assert [p["nome"] for p in g["politicos"]] == ["JOSÉ TIVERON"] and g["pendente"] is None
        assert api.get("/api/politicos", params={"cargo": "vereador"}).json()["total"] > 0
    finally:
        app.dependency_overrides.clear()


def test_padrao_das_travas_e_a_decisao_vigente(monkeypatch):
    from rastro.config import get_settings
    from rastro.politicos import publicacao

    for v in (
        "RASTRO_POL_PUBLICAR_TSE",
        "RASTRO_POL_PUBLICAR_TSE_2026",
        "RASTRO_POL_PUBLICAR_EMENDAS",
    ):
        monkeypatch.delenv(v, raising=False)
    get_settings.cache_clear()
    assert (publicacao.tse(), publicacao.tse_2026(), publicacao.emendas()) == (True, True, True)


@respx.mock
def test_eleitos_2026_ficam_ocultos_ate_a_trava(session, cliente, monkeypatch):
    """Amostra real do arquivo de 2026 (gerado pelo TSE em 05/10/2026), sem colunas pessoais."""
    from fastapi.testclient import TestClient

    from rastro.api.main import app
    from rastro.db import get_session
    from rastro.models import Municipio

    session.add(Municipio(cod_ibge=3500105, nome="Adamantina", uf="SP", regiao="SE"))
    session.commit()
    _mock()
    respx.get(tse.URL_CANDIDATOS.format(ano=2026)).respond(content=_zip_original(2026))
    r = tse.coletar_eleitos(session, cliente, 2026, "SP", set())
    amostra = list(
        csv.DictReader(
            io.StringIO((POL / "tse_consulta_cand_2026_SP_amostra.csv").read_text()),
            delimiter=";",
        )
    )
    assert r["eleitos"] == sum(1 for x in amostra if x["DS_SIT_TOT_TURNO"] in tse.ELEITO) == 6
    gov = session.scalars(
        select(PolPolitico).where(
            PolPolitico.eleicao_ano == 2026, PolPolitico.cargo == "governador"
        )
    ).one()
    assert gov.situacao_candidatura and gov.data_divulgacao is not None
    app.dependency_overrides[get_session] = lambda: session
    try:
        api = TestClient(app)
        _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE_2026", "0")
        assert api.get(f"/api/politicos/{gov.id}").status_code == 404
        secoes = api.get("/api/municipios/3500105/representantes").json()["secoes"]
        assert not any("2026" in s["titulo"] for s in secoes)
        _trava(monkeypatch, "RASTRO_POL_PUBLICAR_TSE_2026", "1")
        assert api.get(f"/api/politicos/{gov.id}").status_code == 200
        [s26] = [
            s
            for s in api.get("/api/municipios/3500105/representantes").json()["secoes"]
            if "2026" in s["titulo"]
        ]
        assert "mandato a partir de 2027" in s26["titulo"]
    finally:
        app.dependency_overrides.clear()
