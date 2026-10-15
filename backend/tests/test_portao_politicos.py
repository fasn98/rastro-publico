"""Portão de políticos por UF e o registro de cada coleta por UF (pol_coleta_uf).

Respostas reais gravadas em tests/fixtures/politicos (as mesmas de test_politicos,
test_cota_emendas e test_tse).
"""

import httpx
import pytest
import respx
from sqlalchemy import select
from test_politicos import JSON, _json, _mock_camara
from test_tse import AMOSTRA_IBGE
from test_tse import _mock as _mock_tse

from rastro.coletores.arquivo import ArquivoBruto
from rastro.coletores.base import ColetaParcial, novo_cliente
from rastro.models import Coleta
from rastro.politicos import camara, coletar, tse
from rastro.politicos import portao as pp
from rastro.politicos.modelos import PolColetaUf


@pytest.fixture
def cliente(engine):
    with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
        yield c


def _coleta(session, fonte: str, status: str, erro: str | None = None) -> Coleta:
    c = Coleta(fonte=fonte, status=status, erro=erro)
    session.add(c)
    session.commit()
    return c


def _registrar(session, fonte: str, ufs: list[str], status: str = "sucesso") -> None:
    coletar.registrar_ufs(session, _coleta(session, fonte, status), fonte, ufs)


# ------------------------------------------------------------------ registro por UF


def test_registro_por_uf_usa_o_status_da_execucao(session):
    c = _coleta(session, "pol-emendas", "parcial", "emendas 2025: HTTPStatusError\ntraceback")
    coletar.registrar_ufs(session, c, "pol-emendas", ["SP", "SC"])
    linhas = session.scalars(select(PolColetaUf).order_by(PolColetaUf.uf)).all()
    assert [(x.uf, x.status, x.motivo) for x in linhas] == [
        ("SC", "parcial", "emendas 2025: HTTPStatusError"),
        ("SP", "parcial", "emendas 2025: HTTPStatusError"),
    ]


def _mock_camara_completa():
    _mock_camara()
    respx.get(url__regex=rf"{camara.API}/deputados/\d+/historico").respond(
        content=_json("camara_historico_220637.json"), headers=JSON
    )


@respx.mock
def test_camara_parcial_por_falha_de_um_deputado_marca_a_uf_dele(session, cliente):
    # o histórico de um deputado de SP falha (404 não é transitório: não há nova tentativa);
    # a rota específica vem antes da geral, que o respx usa a primeira que casa
    respx.get(f"{camara.API}/deputados/204534/historico").respond(404)
    _mock_camara_completa()
    coletor = coletar.coletor_camara(["SP"], [2025])
    respx.get(url__startswith=camara.ARQUIVOS).respond(404)  # arquivos anuais: não importam
    respx.get(url__startswith="https://www.camara.leg.br/cotas/").respond(404)
    with pytest.raises(ColetaParcial):
        coletor(session, cliente)
    status, motivo = coletor.por_uf["SP"]
    assert status == "parcial" and "histórico 204534" in motivo


@respx.mock
def test_camara_com_prazo_esgotado_marca_todas_as_ufs(session, cliente):
    _mock_camara_completa()
    relogio = iter([0.0, 999.0])  # o prazo acaba antes do primeiro item
    prazo = coletar.Prazo(1, relogio=lambda: next(relogio))
    coletor = coletar.coletor_camara(["SP"], [2025], prazo)
    with pytest.raises(ColetaParcial):
        coletor(session, cliente)
    assert coletor.por_uf == {"SP": ("parcial", "limite de tempo de 1 min atingido")}


# ------------------------------------------------------------------ portão


def test_uf_sem_nada_coletado_e_reprovada_com_motivos_claros(session):
    r = pp.avaliar_uf(session, "SC")
    assert not r["aprovada"]
    assert "emendas da UF ainda não coletadas" in r["motivos"]
    assert "deputados federais (Câmara) da UF ainda não coletados" in r["motivos"]
    assert "nenhum eleito do TSE de 2022 gravado para a UF" in r["motivos"]


@respx.mock
def test_uf_com_tudo_coletado_e_aprovada(session, cliente):
    _mock_tse()
    tse.coletar_eleitos(session, cliente, 2022, "SP", set())
    tse.coletar_eleitos(session, cliente, 2024, "SP", AMOSTRA_IBGE)
    for fonte in pp.FONTES:
        _registrar(session, fonte, ["SP"])
    r = pp.avaliar_uf(session, "SP")
    assert r == {"aprovada": True, "motivos": []}


@respx.mock
def test_ultima_coleta_parcial_reprova(session, cliente):
    _mock_tse()
    tse.coletar_eleitos(session, cliente, 2022, "SP", set())
    tse.coletar_eleitos(session, cliente, 2024, "SP", AMOSTRA_IBGE)
    for fonte in pp.FONTES:
        _registrar(session, fonte, ["SP"])
    _registrar(session, "pol-senado", ["SP"], "parcial")  # a mais recente vale
    r = pp.avaliar_uf(session, "SP")
    assert r["motivos"] == ["senadores (Senado): última coleta terminou parcial"]


@respx.mock
def test_uf_sem_eleitos_de_2024_e_reprovada(session, cliente):
    _mock_tse()
    tse.coletar_eleitos(session, cliente, 2022, "SP", set())  # só 2022
    for fonte in pp.FONTES:
        _registrar(session, fonte, ["SP"])
    assert pp.avaliar_uf(session, "SP")["motivos"] == [
        "nenhum eleito do TSE de 2024 gravado para a UF"
    ]


def test_df_nao_precisa_de_eleitos_de_2024(session):
    for fonte in pp.FONTES:
        _registrar(session, fonte, ["DF"])
    # o DF não tem eleição municipal: só 2022 aparece nos motivos
    assert pp.avaliar_uf(session, "DF")["motivos"] == [
        "nenhum eleito do TSE de 2022 gravado para a UF"
    ]


@respx.mock
def test_excecao_aprovada_sem_linha_no_arquivo_reprova(session, cliente):
    _mock_camara()
    with httpx.Client() as c:
        camara.coletar_deputados(session, c, "SP")  # inclui João Cury e Ribamar Silva
    r = pp.avaliar_uf(session, "SP")
    excecoes = [m for m in r["motivos"] if m.startswith("exceção aprovada")]
    assert len(excecoes) == 2 and any("JOAO CURY NETO" in m for m in excecoes)
    # as exceções são de deputados de SP: não pesam em outra UF
    assert not [m for m in pp.avaliar_uf(session, "SC")["motivos"] if "exceção" in m]


def test_prefeitos_so_contam_com_a_trava_das_gestoes(session, monkeypatch):
    from rastro.config import get_settings

    assert not [m for m in pp.avaliar_uf(session, "SC")["motivos"] if "prefeitos" in m]
    monkeypatch.setenv("RASTRO_POL_PUBLICAR_GESTOES", "1")
    get_settings.cache_clear()
    try:
        motivos = pp.avaliar_uf(session, "SC")["motivos"]
    finally:
        get_settings.cache_clear()
    assert "prefeitos eleitos (TSE) da UF ainda não coletados" in motivos


def test_erro_na_avaliacao_reprova_sem_derrubar(session, monkeypatch):
    def quebra(*_):
        raise RuntimeError("banco fora")

    monkeypatch.setattr(pp, "avaliar_uf", quebra)
    r = pp.avaliar_uf_isolado(session, "SC")
    assert r == {
        "aprovada": False,
        "motivos": ["avaliação não pôde ser feita (RuntimeError: banco fora)"],
    }
