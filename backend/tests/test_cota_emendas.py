"""Cota parlamentar (Câmara) e emendas pelo arquivo em lote do Portal da Transparência.

Amostras reais em tests/fixtures/politicos:
- camara_cota_2025_SP_amostra.csv: linhas do arquivo anual Ano-2025.csv (06/10/2026), já
  SEM as colunas pessoais e com CPF/nome de fornecedor pessoa física apagados. Para testar
  a redação, o teste remonta o layout original preenchendo esses campos com MARCADORES.
- transparencia_emendas_amostra.csv: 9 linhas do EmendasParlamentares.csv (06/10/2026),
  que não tem dados pessoais.
"""

import csv
import gzip
import io
import zipfile
from decimal import Decimal

import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from conftest import FIXTURES
from rastro.api.main import app
from rastro.coletores.arquivo import ArquivoBruto, sha256
from rastro.coletores.base import novo_cliente
from rastro.db import get_session
from rastro.models import Municipio, PayloadBruto, RespostaBruta
from rastro.politicos import camara, transparencia
from rastro.politicos.modelos import PolDespesaCota, PolEmenda

POL = FIXTURES / "politicos"


def _trava(monkeypatch, nome: str, valor: str) -> None:
    """Liga/desliga uma trava de publicação (Settings) durante o teste."""
    from rastro.config import get_settings

    monkeypatch.setenv(nome, valor)
    get_settings.cache_clear()


# cabeçalho real do Ano-2025.csv, na ordem original
CABECALHO_COTA = (
    "txNomeParlamentar;cpf;ideCadastro;nuCarteiraParlamentar;nuLegislatura;sgUF;sgPartido;"
    "codLegislatura;numSubCota;txtDescricao;numEspecificacaoSubCota;txtDescricaoEspecificacao;"
    "txtFornecedor;txtCNPJCPF;txtNumero;indTipoDocumento;datEmissao;vlrDocumento;vlrGlosa;"
    "vlrLiquido;numMes;numAno;numParcela;txtPassageiro;txtTrecho;numLote;numRessarcimento;"
    "datPagamentoRestituicao;vlrRestituicao;nuDeputadoId;ideDocumento;urlDocumento"
).split(";")
CPF_MARCADOR = "99999999999"  # 11 dígitos: marcador de teste, não é dado real
CPF_NO_NOME = "99999999998"


def _ler(nome: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO((POL / nome).read_text()), delimiter=";"))


def _zip_cota() -> bytes:
    saida = io.StringIO()
    w = csv.DictWriter(saida, CABECALHO_COTA, delimiter=";", quoting=csv.QUOTE_ALL)
    w.writeheader()
    for i, r in enumerate(_ler("camara_cota_2025_SP_amostra.csv")):
        r = {**r, "cpf": f"MARCADOR-TESTE-CPF-{i}", "nuCarteiraParlamentar": f"MARCADOR-TESTE-{i}"}
        r["txtPassageiro"] = f"MARCADOR-TESTE-PASSAGEIRO-{i}"
        if r["txtCNPJCPF"] == "" and r["txtFornecedor"] == "":
            r["txtCNPJCPF"], r["txtFornecedor"] = CPF_MARCADOR, f"MARCADOR-TESTE-PF-{i}"
        elif i == 3:  # primeira linha de pessoa jurídica da amostra
            # razão social de MEI traz o CPF do titular no nome (como na fonte)
            r["txtFornecedor"] += f" {CPF_NO_NOME}"
        w.writerow(r)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Ano-2025.csv", saida.getvalue().encode("utf-8-sig"))
    return buf.getvalue()


def _zip_emendas() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        texto = (POL / "transparencia_emendas_amostra.csv").read_text()
        z.writestr("EmendasParlamentares.csv", texto.replace("\n", "\r\n").encode("latin-1"))
    return buf.getvalue()


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


def _tudo(session) -> list[bytes]:
    tabelas = session.execute(
        text("select tablename from pg_tables where schemaname = 'public'")
    ).scalars()
    linhas = [
        x.encode()
        for t in tabelas
        for x in session.execute(text(f'select row_to_json(y)::text from "{t}" y')).scalars()
    ]
    return linhas + [gzip.decompress(p.conteudo) for p in session.scalars(select(PayloadBruto))]


@respx.mock
def test_cota_grava_sem_dados_pessoais(session, cliente, deputados):
    original = _zip_cota()
    respx.get(camara.URL_COTA.format(ano=2025)).respond(content=original)
    n = camara.coletar_cota(session, cliente, 2025, "SP", deputados)
    amostra = _ler("camara_cota_2025_SP_amostra.csv")
    assert n == sum(1 for r in amostra if int(r["ideCadastro"]) in deputados) == 36
    tabata = session.scalar(
        select(func.sum(PolDespesaCota.valor_liquido)).where(
            PolDespesaCota.politico_id == deputados[204534], PolDespesaCota.mes == 1
        )
    )
    assert tabata == Decimal("12327.16")  # soma de vlrLiquido de jan/2025 no arquivo
    pf = session.scalars(select(PolDespesaCota).where(PolDespesaCota.pessoa_fisica)).all()
    assert len(pf) == 3 and all(d.fornecedor is None and d.cnpj is None for d in pf)
    r = session.scalars(select(RespostaBruta).where(RespostaBruta.url.like("%cotas%"))).one()
    assert r.sha256_original == sha256(original)
    assert r.campos_removidos == [
        "cpf",
        "nuCarteiraParlamentar",
        "txtPassageiro",
        "txtCNPJCPF (3 linhas)",
        "txtFornecedor (3 linhas)",
        "txtFornecedor (CPF no nome) (1 linhas)",
    ]
    assert (
        session.scalar(
            select(func.count())
            .select_from(PolDespesaCota)
            .where(PolDespesaCota.fornecedor.like("%[CPF removido]"))
        )
        == 1
    )
    for conteudo in _tudo(session):
        assert b"MARCADOR-TESTE" not in conteudo and CPF_MARCADOR.encode() not in conteudo
        assert CPF_NO_NOME.encode() not in conteudo


@respx.mock
def test_emendas_do_arquivo_com_codigo_ibge_oficial(session, cliente, deputados):
    original = _zip_emendas()
    respx.get(transparencia.URL_ARQUIVO).respond(content=original)
    from rastro.politicos.vinculo import Autor

    # deputados da legislatura 57: orçamentos de 2024 a 2027 (votados de 2023 a 2026)
    autores = {
        transparencia.normalizar_nome(n): Autor(deputados[i], n, 2024, 2027)
        for n, i in (
            ("Tabata Amaral", 204534),
            ("Missionário José Olimpio", 160561),
            ("Pr. Marco Feliciano", 160601),
        )
    }
    r = transparencia.coletar_arquivo(session, cliente, "SP", 2023, autores)
    # fora do recorte: a de 2022 e a da Bahia de autor de outra UF
    assert r["linhas"] == 7
    # emenda de 2023 (orçamento votado em 2022, legislatura anterior): fora do mandato
    assert r["fora_do_mandato"] == {"PR. MARCO FELICIANO": 1, "TABATA AMARAL": 1}
    por_codigo = {e.codigo_emenda: e for e in session.scalars(select(PolEmenda))}
    assert por_codigo["202441320023"].cod_ibge_destino == 3551009  # São Vicente
    assert por_codigo["202441320023"].transferencia_especial
    assert por_codigo["202441320023"].politico_id == deputados[204534]
    # "EMBU - SP" (nome antigo) não casa por texto, mas o código oficial resolve
    assert por_codigo["202328120015"].cod_ibge_destino == 3515004
    assert por_codigo["202328120015"].politico_id is None  # 2023: sem link, nome da fonte
    # autor com sufixo "(EX-PARLAMENTAR ...)" casa pelo nome antes do parêntese
    herdada = por_codigo["202630880003"]
    assert herdada.politico_id == deputados[160561] and "EX-PARLAMENTAR" in herdada.nome_autor
    assert por_codigo["202341320005"].cod_ibge_destino is None  # MÚLTIPLO
    assert por_codigo["202339070002"].valor_pago == Decimal("14662883.00")
    assert sum(e.transferencia_especial for e in por_codigo.values()) == 3
    resp = session.scalars(
        select(RespostaBruta).where(RespostaBruta.url == transparencia.URL_ARQUIVO)
    ).one()
    assert resp.sha256_original == sha256(original) and resp.campos_removidos == []


@respx.mock
def test_emendas_do_arquivo_fora_de_sp(session, cliente):
    """Antes, só SP tinha nome no recorte (KeyError 'AC'). Linha real da Bahia na amostra."""
    respx.get(transparencia.URL_ARQUIVO).respond(content=_zip_emendas())
    r = transparencia.coletar_arquivo(session, cliente, "BA", 2023, {})
    assert r["linhas"] == 1
    emenda = session.scalars(select(PolEmenda)).one()
    assert emenda.codigo_emenda == "202528710001" and emenda.cod_ibge_destino == 2924405


@respx.mock
def test_emendas_de_varias_ufs_numa_passada(session, cliente):
    """A gravação substitui as linhas do arquivo: as UFs vão juntas, sem apagar uma à outra."""
    respx.get(transparencia.URL_ARQUIVO).respond(content=_zip_emendas())
    linhas = {
        uf: transparencia.coletar_arquivo(session, cliente, uf, 2023, {})["linhas"]
        for uf in ("SP", "BA")
    }
    # coletar a BA depois de SP apaga SP: por isso as UFs vão numa passada só
    assert session.scalar(select(func.count()).select_from(PolEmenda)) == linhas["BA"] == 1
    r = transparencia.coletar_arquivo(session, cliente, ["SP", "BA"], 2023, {})
    assert r["linhas"] == linhas["SP"] + linhas["BA"]
    assert session.scalar(select(func.count()).select_from(PolEmenda)) == r["linhas"]


def test_nomes_de_todas_as_ufs():
    # 26 estados e o DF, sem nome repetido (um nome levaria a duas UFs)
    assert len(transparencia.NOMES_UF) == len(set(transparencia.NOMES_UF.values())) == 27


@respx.mock
def test_api_emendas_so_publica_com_a_trava_ligada(session, cliente, deputados, monkeypatch):
    from rastro.coletores.base import executar

    session.add(Municipio(cod_ibge=3509502, nome="Campinas", uf="SP", regiao="SE"))
    session.commit()
    respx.get(transparencia.URL_ARQUIVO).respond(content=_zip_emendas())

    def coletar(s, c):
        return transparencia.coletar_arquivo(s, c, "SP", 2023, {})["linhas"]

    executar(session, "pol-emendas", coletar, cliente)
    app.dependency_overrides[get_session] = lambda: session
    try:
        api = TestClient(app)
        _trava(monkeypatch, "RASTRO_POL_PUBLICAR_EMENDAS", "0")
        e = api.get("/api/municipios/3509502/emendas").json()
        assert e["coletadas"] and not e["publicadas"] and e["itens"] == []
        _trava(monkeypatch, "RASTRO_POL_PUBLICAR_EMENDAS", "1")
        e = api.get("/api/municipios/3509502/emendas").json()
        assert e["publicadas"] and [x["codigo_emenda"] for x in e["itens"]] == ["202339090001"]
        [autor] = e["por_parlamentar"]
        assert (autor["nome_autor"], Decimal(autor["valor_pago"])) == (
            "ALEXIS FONTEYNE",
            Decimal("13033674.00"),
        )
    finally:
        app.dependency_overrides.clear()


def test_vinculo_recusa_nome_ambiguo_ou_ausente(session, deputados):
    from rastro.politicos import vinculo

    # identificadores "teste:*" são marcadores de teste, não parlamentares reais
    universo = {
        transparencia.normalizar_nome("Tabata Amaral"): {"camara:204534"},
        transparencia.normalizar_nome("Pr. Marco Feliciano"): {"camara:160601", "teste:1"},
    }
    autores, recusados = vinculo.autores_confirmaveis(session, "SP", universo)
    assert set(autores) == {"TABATA AMARAL"}
    assert autores["TABATA AMARAL"].politico_id == deputados[204534]
    assert (autores["TABATA AMARAL"].primeiro_ano, autores["TABATA AMARAL"].ultimo_ano) == (
        2024,
        2027,
    )
    assert "outro parlamentar" in recusados["Pr. Marco Feliciano"]
    assert recusados["Adilson Barroso"] == "não encontrado na lista da legislatura"


@respx.mock
def test_codigo_de_autor_diferente_desfaz_o_vinculo(session, cliente, deputados):
    from rastro.politicos.vinculo import Autor

    # o mesmo parlamentar com dois "Código do Autor" no arquivo: não liga nenhuma
    texto = (POL / "transparencia_emendas_amostra.csv").read_text()
    linhas = texto.splitlines()
    tabata = [x for x in linhas if '"TABATA AMARAL"' in x and '"2024"' in x][0]
    outra = tabata.replace('"4132"', '"MARCADOR-TESTE"').replace('"202441320023"', '"T-1"')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("EmendasParlamentares.csv", "\r\n".join([*linhas, outra]).encode("latin-1"))
    respx.get(transparencia.URL_ARQUIVO).respond(content=buf.getvalue())
    autores = {"TABATA AMARAL": Autor(deputados[204534], "Tabata Amaral", 2024, 2027)}
    r = transparencia.coletar_arquivo(session, cliente, "SP", 2023, autores)
    assert r["codigo_de_autor_ambiguo"] == [deputados[204534]] and r["ligadas"] == 0
