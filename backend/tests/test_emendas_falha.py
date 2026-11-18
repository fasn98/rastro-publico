"""Falha na coleta de emendas de uma UF já publicada (decisão do Fabio, 17/11/2026, ADR-0024).

- O site segue com os dados anteriores: a transação da coleta que falhou não apaga nada, o
  portão não reprova a UF e o manifesto traz a data dos dados ("Dados de dd/mm/aaaa; a
  coleta mais recente não foi concluída").
- Mais de 7 dias sem coleta concluída: aviso destacado (`desatualizada`), sem tirar a UF.
- Cada falha vai para o log da coleta e para o resumo da execução, com a UF e o motivo (só
  o tipo do erro).

A coleta com sucesso usa as respostas reais de `test_vinculo_ufs` (arquivo do Portal de
13/11/2026, Câmara e Senado de 17/11/2026). A falha é o Portal respondendo HTTP 504, como a
API da Câmara fez nas coletas de novembro de 2026; nenhum dado é inventado.
"""

import gzip
import json
import logging
from datetime import timedelta

import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from test_vinculo_ufs import HELIO_LOPES, JSON, POL, _deputados, _liberar, _zip_emendas
from test_vinculo_ufs import coletado as _coletado

from rastro import site
from rastro.api.main import app
from rastro.coletores.arquivo import ArquivoBruto
from rastro.coletores.base import novo_cliente
from rastro.config import get_settings
from rastro.db import get_session
from rastro.fontes import executar_com_esperas
from rastro.models import Coleta
from rastro.politicos import camara, coletar, senado, situacao_emendas, transparencia
from rastro.politicos import portao as pp
from rastro.politicos.modelos import PolColetaUf, PolEmenda

coletado = _coletado  # fixture de test_vinculo_ufs: municípios e deputados de SP e do RJ
FONTE_EMENDAS = {"pol-emendas": pp.FONTES["pol-emendas"]}


def _rodar(banco, engine, ufs: list[str], falhar: bool = False) -> Coleta:
    """Uma execução da coleta de emendas do arquivo, como `rastro politicos --fontes
    emendas`: com as esperas, e o resultado gravado por UF."""
    with respx.mock:
        rota = respx.get(transparencia.URL_ARQUIVO)
        if falhar:
            rota.respond(status_code=504)
        else:
            rota.respond(content=_zip_emendas())
        respx.get(f"{camara.API}/deputados").mock(side_effect=_deputados)
        respx.get(f"{senado.API}/senador/lista/legislatura/57.json").respond(
            content=gzip.decompress((POL / "senado_senadores_leg57.json.gz").read_bytes()),
            headers=JSON,
        )
        coleta = executar_com_esperas(
            banco,
            "pol-emendas",
            coletar.coletor_emendas_arquivo(ufs, [2024, 2025, 2026]),
            lambda: novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)),
            esperas=[],
        )
    coletar.registrar_ufs(banco, coleta, "pol-emendas", ufs)
    return coleta


def _linhas(banco) -> list[tuple]:
    return banco.execute(
        select(PolEmenda.codigo_emenda, PolEmenda.politico_id, PolEmenda.valor_pago).order_by(
            PolEmenda.codigo_emenda
        )
    ).all()


def _falha(banco, uf: str) -> PolColetaUf:
    return banco.scalar(
        select(PolColetaUf)
        .where(PolColetaUf.uf == uf, PolColetaUf.status != "sucesso")
        .order_by(PolColetaUf.id)
        .limit(1)
    )


def test_falha_mantem_os_dados_anteriores_e_nao_reprova_a_uf(coletado, engine, monkeypatch, caplog):
    banco, ids = coletado
    _liberar(monkeypatch, "RJ")  # UF já publicada, como SC hoje
    ok = _rodar(banco, engine, ["SP", "RJ"])
    assert ok.status == "sucesso"
    antes = _linhas(banco)
    assert len(antes) == 3

    with caplog.at_level(logging.WARNING, logger="rastro.politicos.coletar"):
        falha = _rodar(banco, engine, ["SP", "RJ"], falhar=True)
    assert falha.status == "falha"
    assert _linhas(banco) == antes  # nada apagado: o vínculo do autor do RJ continua
    helio = banco.scalar(select(PolEmenda).where(PolEmenda.codigo_emenda == "202441020011"))
    assert helio.politico_id == ids["rj"][HELIO_LOPES]

    # log da coleta: uma linha por UF, com o motivo (só o tipo do erro)
    avisos = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    for uf in ("RJ", "SP"):
        assert f"pol-emendas {uf}: coleta não concluída (HTTP 504 após 1 tentativa)" in avisos

    sit = situacao_emendas.situacao(banco, "RJ")
    assert sit == {
        "dados_de": ok.finalizada_em.isoformat(),
        "falha_desde": _falha(banco, "RJ").registrada_em.isoformat(),
        "motivo": "HTTP 504 após 1 tentativa",
        "dados_anteriores": True,
        "desatualizada": False,
    }
    assert pp._coletas(banco, "RJ", FONTE_EMENDAS) == []  # o portão não reprova


def test_mais_de_7_dias_sem_coleta_concluida_marca_a_uf_desatualizada(
    coletado, engine, monkeypatch
):
    banco, _ = coletado
    _liberar(monkeypatch, "RJ")
    _rodar(banco, engine, ["SP", "RJ"])
    _rodar(banco, engine, ["SP", "RJ"], falhar=True)
    _rodar(banco, engine, ["SP", "RJ"], falhar=True)  # a contagem parte da primeira falha
    desde = _falha(banco, "RJ").registrada_em
    assert situacao_emendas.situacao(banco, "RJ")["falha_desde"] == desde.isoformat()
    sete = situacao_emendas.situacao(banco, "RJ", agora=desde + timedelta(days=7))
    assert not sete["desatualizada"]
    oito = situacao_emendas.situacao(banco, "RJ", agora=desde + timedelta(days=7, seconds=1))
    assert oito["desatualizada"] and oito["dados_anteriores"]
    assert pp._coletas(banco, "RJ", FONTE_EMENDAS) == []  # continua no site

    # uma coleta concluída encerra a falha
    _rodar(banco, engine, ["SP", "RJ"])
    assert situacao_emendas.situacao(banco, "RJ") is None


def test_sem_dados_anteriores_a_falha_reprova_como_antes(coletado, engine, monkeypatch):
    banco, _ = coletado
    _liberar(monkeypatch, "RJ")
    _rodar(banco, engine, ["SP", "RJ"], falhar=True)
    sit = situacao_emendas.situacao(banco, "RJ")
    assert sit["dados_de"] is None and not sit["dados_anteriores"]
    assert pp._coletas(banco, "RJ", FONTE_EMENDAS) == [
        "emendas: última coleta terminou falha (HTTP 504 após 1 tentativa)"
    ]


def test_dados_anteriores_so_valem_se_a_ultima_coleta_concluida_incluiu_a_uf(
    coletado, engine, monkeypatch
):
    """Uma coleta concluída sem a UF regrava todas as linhas: as da UF ficam incompletas."""
    banco, _ = coletado
    _liberar(monkeypatch, "RJ")
    _rodar(banco, engine, ["SP", "RJ"])
    _rodar(banco, engine, ["SP"])
    _rodar(banco, engine, ["SP", "RJ"], falhar=True)
    assert not situacao_emendas.situacao(banco, "RJ")["dados_anteriores"]
    assert situacao_emendas.situacao(banco, "SP")["dados_anteriores"]
    assert pp._coletas(banco, "RJ", FONTE_EMENDAS)
    assert pp._coletas(banco, "SP", FONTE_EMENDAS) == []


def test_resumo_da_execucao_traz_cada_uf_com_o_motivo(coletado, engine, monkeypatch):
    banco, _ = coletado
    _liberar(monkeypatch, "RJ")
    ok = _rodar(banco, engine, ["SP", "RJ"])
    inicio = banco.scalar(select(func.now()))
    _rodar(banco, engine, ["SP", "RJ"], falhar=True)
    desde = _falha(banco, "RJ").registrada_em
    falhas = situacao_emendas.falhas_desde(banco, inicio)
    assert [f["uf"] for f in falhas] == ["RJ", "SP"]
    dia_ok, dia_falha = ok.finalizada_em.isoformat()[:10], desde.isoformat()[:10]
    detalhe = (
        f"HTTP 504 após 1 tentativa; dados de {dia_ok}; sem coleta concluída desde {dia_falha}"
    )
    assert situacao_emendas.resumo(falhas) == (
        f"Emendas por UF com falha: RJ ({detalhe}); SP ({detalhe})"
    )

    # mais de 7 dias: o resumo destaca a UF
    banco.execute(
        update(PolColetaUf)
        .where(PolColetaUf.status != "sucesso")
        .values(registrada_em=PolColetaUf.registrada_em - timedelta(days=8))
    )
    banco.commit()
    assert "DESATUALIZADA (mais de 7 dias)" in situacao_emendas.resumo(
        situacao_emendas.falhas_desde(banco, None)
    )

    _rodar(banco, engine, ["SP", "RJ"])
    assert situacao_emendas.resumo(situacao_emendas.falhas_desde(banco, None)) == (
        "Emendas por UF com falha: nenhuma"
    )


def test_nota_sem_municipio_segue_com_os_dados_anteriores(coletado, engine, monkeypatch):
    banco, _ = coletado
    _liberar(monkeypatch, "")
    monkeypatch.setenv("RASTRO_POL_PUBLICAR_EMENDAS", "1")
    get_settings.cache_clear()
    _rodar(banco, engine, ["SP", "RJ"])
    app.dependency_overrides[get_session] = lambda: banco
    try:
        api = TestClient(app)
        antes = api.get("/api/ufs/SP/emendas-sem-municipio")
        assert antes.status_code == 200
        _rodar(banco, engine, ["SP", "RJ"], falhar=True)
        depois = api.get("/api/ufs/SP/emendas-sem-municipio")
        assert depois.status_code == 200 and depois.json() == antes.json()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("dias", [0, 8])
def test_manifesto_traz_a_data_dos_dados_e_o_aviso_de_7_dias(
    coletado, engine, tmp_path, monkeypatch, dias
):
    banco, _ = coletado
    _liberar(monkeypatch, "")
    monkeypatch.setenv("RASTRO_POL_PUBLICAR_EMENDAS", "1")
    get_settings.cache_clear()
    ok = _rodar(banco, engine, ["SP", "RJ"])
    dados = tmp_path / "dados"
    assert site.exportar(dados, "SP", banco)["emendas_coleta"] == {}

    _rodar(banco, engine, ["SP", "RJ"], falhar=True)
    if dias:  # o tempo passa: a falha foi registrada há `dias` dias
        banco.execute(
            update(PolColetaUf)
            .where(PolColetaUf.status != "sucesso")
            .values(registrada_em=PolColetaUf.registrada_em - timedelta(days=dias))
        )
        banco.commit()
    manifesto = site.exportar(dados, "SP", banco)
    assert manifesto["emendas_coleta"] == {
        "SP": {
            "dados_de": ok.finalizada_em.isoformat(),
            "falha_desde": _falha(banco, "SP").registrada_em.isoformat(),
            "dados_anteriores": True,
            "desatualizada": dias > 7,
        }
    }
    assert json.loads((dados / "manifesto.json").read_text())["emendas_coleta"]["SP"]
    assert site.verificar(dados) == []
    # a UF RJ não está no site (não liberada): fica fora do manifesto
    assert "RJ" not in manifesto["emendas_coleta"]
