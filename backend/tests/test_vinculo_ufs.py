"""Regra 5 do vínculo de emendas (decisão do Fabio, 17/11/2026): o vínculo emenda → autor só é
gravado quando a UF do autor está publicada (SP, a UF da exportação, ou uma UF de
`RASTRO_POL_UFS_LIBERADAS`).

Respostas reais gravadas:

- `transparencia_emendas_20261113_ufs.csv`: 3 linhas do `EmendasParlamentares.csv` do arquivo
  em lote do Portal da Transparência
  (https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/emendas-parlamentares/EmendasParlamentares.zip,
  Last-Modified 13/11/2026 19:24:48 GMT, 47.094.995 bytes, SHA-256 do ZIP
  ad1075230ce3c3f3b908fa03e7fa38d25c0f597d6f32ebd367389cfd5b9215b4), com o cabeçalho
  de 29 colunas (o Portal acrescentou "Possui Apoiador/Solicitante?"):
  - 202441020011: Helio Lopes (deputado do RJ) para São Paulo (SP), 2024;
  - 202536110009: Luiza Erundina (deputada de SP) para São Paulo (SP), 2025;
  - 202436110016: Luiza Erundina para Esteio (RS), 2024.
- `camara_deputados_rj_atual.json` e `camara_deputados_rj_leg57.json`: respostas da API da
  Câmara (/deputados?siglaUf=RJ, sem e com idLegislatura=57), em 17/11/2026.

Caso pedido (autor do RS e município de SP): no arquivo de 13/11/2026, nenhum parlamentar do
RS da legislatura 57 tem emenda de 2023 em diante para município de SP ou de SC. O caso real
mais próximo é o de um deputado do RJ (UF também não liberada) para São Paulo, usado aqui.
"""

import io
import json
import zipfile

import httpx
import pytest
import respx
from sqlalchemy import select

from conftest import FIXTURES, carregar
from rastro import site
from rastro.coletores import ibge
from rastro.coletores.arquivo import ArquivoBruto
from rastro.coletores.base import executar, novo_cliente
from rastro.config import get_settings
from rastro.models import Municipio
from rastro.politicos import camara, coletar, transparencia, vinculo
from rastro.politicos.modelos import PolEmenda

POL = FIXTURES / "politicos"
JSON = {"content-type": "application/json"}
HELIO_LOPES = 204444  # id na Câmara, RJ
ERUNDINA = 74784  # id na Câmara, SP
SAO_PAULO, ESTEIO = 3550308, 4307708


def _deputados(request: httpx.Request) -> httpx.Response:
    from test_politicos import _deputados as _deputados_sp

    p = request.url.params
    if p.get("siglaUf") != "RJ":
        return _deputados_sp(request)
    nome = (
        "camara_deputados_rj_leg57.json"
        if "idLegislatura" in p
        else "camara_deputados_rj_atual.json"
    )
    return httpx.Response(200, content=(POL / nome).read_bytes(), headers=JSON)


def _zip_emendas() -> bytes:
    texto = (POL / "transparencia_emendas_20261113_ufs.csv").read_text()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("EmendasParlamentares.csv", texto.replace("\n", "\r\n").encode("latin-1"))
    return buf.getvalue()


def _liberar(monkeypatch, ufs: str):
    monkeypatch.setenv("RASTRO_POL_UFS_LIBERADAS", ufs)
    get_settings.cache_clear()


@pytest.fixture
def coletado(session, engine, monkeypatch):
    """Municípios do IBGE (Adamantina, São Paulo e Boa Esperança do Norte, resposta real) e os
    deputados de SP e do RJ da legislatura 57, pelos coletores reais."""
    session.add_all(Municipio(**ibge.normalizar(m)) for m in carregar("ibge_municipios.json"))
    session.commit()
    with respx.mock:
        respx.get(f"{camara.API}/deputados").mock(side_effect=_deputados)
        with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
            sp = camara.coletar_deputados(session, c, "SP")
            rj = camara.coletar_deputados(session, c, "RJ")
    assert ERUNDINA in sp and HELIO_LOPES in rj  # premissa
    # a lista da legislatura 57 (Câmara e Senado) vem de `vinculo.universo`; aqui, os dois
    # autores do caso, com os ids reais (nomes únicos na legislatura, conferido em 17/11/2026)
    universo = {
        transparencia.normalizar_nome("Luiza Erundina"): {f"camara:{ERUNDINA}"},
        transparencia.normalizar_nome("Helio Lopes"): {f"camara:{HELIO_LOPES}"},
    }
    monkeypatch.setattr(vinculo, "universo", lambda client: universo)
    return session, {"sp": sp, "rj": rj}


def _coletar(banco, engine, ufs: list[str]) -> dict[str, PolEmenda]:
    with respx.mock:
        respx.get(transparencia.URL_ARQUIVO).respond(content=_zip_emendas())
        with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
            coleta = executar(
                banco, "pol-emendas", coletar.coletor_emendas_arquivo(ufs, [2024, 2025, 2026]), c
            )
    assert coleta.status == "sucesso", coleta.erro
    return {e.codigo_emenda: e for e in banco.scalars(select(PolEmenda))}


def test_ufs_com_vinculo(monkeypatch):
    _liberar(monkeypatch, "")
    assert vinculo.ufs_com_vinculo(["SP", "SC", "RS"]) == ["SP"]
    _liberar(monkeypatch, "SC")
    assert vinculo.ufs_com_vinculo(["SP", "SC", "RS"]) == ["SC", "SP"]
    _liberar(monkeypatch, "SC, rs")
    assert vinculo.ufs_com_vinculo(["sp", "SC", "RS"]) == ["RS", "SC", "SP"]


def test_autor_de_uf_nao_liberada_fica_sem_vinculo_e_o_site_publica(
    coletado, engine, tmp_path, monkeypatch
):
    """Autor do RJ (não liberado) com emenda para São Paulo: a linha é gravada como na fonte,
    sem vínculo, e a verificação do site passa. A emenda da deputada de SP continua ligada."""
    banco, ids = coletado
    _liberar(monkeypatch, "")
    emendas = _coletar(banco, engine, ["SP", "RJ"])
    helio = emendas["202441020011"]
    assert helio.cod_ibge_destino == SAO_PAULO and helio.nome_autor == "HELIO LOPES"
    assert helio.politico_id is None and helio.vinculo is None
    erundina = ids["sp"][ERUNDINA]
    assert emendas["202536110009"].politico_id == erundina  # SP: ligada como antes

    dados = tmp_path / "dados"
    site.exportar(dados, "SP", banco)
    assert site.verificar(dados) == []
    itens = json.loads((dados / "municipios" / f"{SAO_PAULO}.json").read_text())["emendas"]["itens"]
    por_codigo = {e["codigo_emenda"]: e for e in itens}
    assert por_codigo["202441020011"]["politico_id"] is None  # sem link na página do município
    assert por_codigo["202536110009"]["politico_id"] == erundina


def test_com_a_uf_liberada_o_vinculo_e_gravado(coletado, engine, monkeypatch):
    """A mesma coleta com o RJ liberado liga a emenda ao deputado: a ausência do vínculo no
    teste anterior vem da regra 5, não de outra regra."""
    banco, ids = coletado
    _liberar(monkeypatch, "RJ")
    emendas = _coletar(banco, engine, ["SP", "RJ"])
    assert emendas["202441020011"].politico_id == ids["rj"][HELIO_LOPES]
    assert emendas["202441020011"].vinculo == "nome"


def test_destino_em_uf_nao_liberada_aparece_so_como_texto(coletado, engine, tmp_path, monkeypatch):
    """Condição do Fabio (17/11/2026): na página da deputada de SP, a emenda para Esteio (RS,
    UF não liberada) mostra o destino como texto. O arquivo do político traz só o texto da
    fonte e o código do IBGE; o site não exporta o município de UF fora do site, e a tela
    (`Politicos.tsx`) mostra `localidade_gasto` como texto, sem link para o município."""
    banco, ids = coletado
    _liberar(monkeypatch, "")
    _coletar(banco, engine, ["SP", "RJ"])
    dados = tmp_path / "dados"
    site.exportar(dados, "SP", banco)
    assert site.verificar(dados) == []
    erundina = ids["sp"][ERUNDINA]
    itens = json.loads((dados / "politicos" / str(erundina) / "emendas" / "2024.json").read_text())[
        "itens"
    ]
    esteio = next(e for e in itens if e["codigo_emenda"] == "202436110016")
    assert esteio["localidade_gasto"] == "ESTEIO - RS" and esteio["cod_ibge_destino"] == ESTEIO
    assert not (dados / "municipios" / f"{ESTEIO}.json").exists()
    assert not any(k in esteio for k in ("url_municipio", "link_municipio", "href"))


def test_api_de_emendas_nao_coleta_uf_nao_liberada(coletado, monkeypatch):
    """A coleta pela API grava cada emenda já ligada ao autor; com a UF não liberada, não
    consulta nada (nenhuma rota simulada: qualquer chamada falharia o teste)."""
    banco, ids = coletado
    _liberar(monkeypatch, "")
    with respx.mock(assert_all_called=False):
        with novo_cliente(req_por_segundo=0) as c:
            assert coletar.coletor_emendas("RJ", [2025])(banco, c) == 0
