"""Site estático: exportação, verificação antes de publicar, publicação e reversão."""

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import carregar
from rastro import publicacao, site
from rastro.api.main import app
from rastro.coletores import ibge
from rastro.db import get_session
from rastro.models import Municipio


@pytest.fixture
def banco(session):
    session.add_all(Municipio(**ibge.normalizar(m)) for m in carregar("ibge_municipios.json"))
    session.commit()
    return session


@pytest.fixture
def exportado(banco, tmp_path):
    dados = tmp_path / "dist" / "dados"
    manifesto = site.exportar(dados, "SP", banco)
    (tmp_path / "dist" / "index.html").write_text("<!doctype html><title>Rastro</title>")
    return tmp_path / "dist", manifesto


def test_exporta_o_mesmo_que_a_api(banco, exportado):
    dist, manifesto = exportado
    dados = dist / "dados"
    lista = json.loads((dados / "municipios.json").read_text())
    # só SP: o fixture tem 2 municípios de SP e 1 de MT
    assert sorted(m["nome"] for m in lista) == ["Adamantina", "São Paulo"]
    assert manifesto["contagens"]["municipios"] == 2
    app.dependency_overrides[get_session] = lambda: banco
    try:
        api = TestClient(app)
        arquivo = json.loads((dados / "municipios" / "3550308.json").read_text())
        assert arquivo["detalhe"] == api.get("/api/municipios/3550308").json()
        assert arquivo["serie"] == api.get("/api/entes/3550308/indicadores/serie").json()
        rep = api.get("/api/municipios/3550308/representantes").json()
        assert arquivo["representantes"]["municipio"] == rep["municipio"]
        grupos = json.loads((dados / arquivo["representantes"]["grupos_ref"]).read_text())
        assert grupos == rep["grupos"]
        # mesmo conteúdo de grupos -> mesmo arquivo para os dois municípios de SP
        outro = json.loads((dados / "municipios" / "3500105.json").read_text())
        assert outro["representantes"]["grupos_ref"] == arquivo["representantes"]["grupos_ref"]
    finally:
        app.dependency_overrides.clear()
    assert (dados / "metodologia.json").exists()
    assert site.verificar(dados) == []


def test_verificacao_bloqueia_dados_faltando(exportado):
    dist, manifesto = exportado
    dados = dist / "dados"
    anterior = {**manifesto, "contagens": {**manifesto["contagens"], "municipios": 645}}
    assert site.verificar(dados, anterior) == ["municipios: 2 na nova versão, 645 na publicada"]
    (dados / "municipios" / "3550308.json").unlink()
    assert "1 municípios sem arquivo de detalhe" in site.verificar(dados)
    (dados / "ranking_quebrado.json").write_text("{nao é json")
    assert any("JSON inválido" in p for p in site.verificar(dados))


# --- publicação (contra um repositório git local, sem rede) -------------------------------


@pytest.fixture
def remoto(tmp_path):
    caminho = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "-q", "--bare", str(caminho)], check=True)
    return str(caminho)


def _ls(remoto: str, *args) -> str:
    return subprocess.run(
        ["git", "ls-remote", *args, remoto], capture_output=True, text=True, check=True
    ).stdout


def _ramo(remoto):
    saida = _ls(remoto, "--heads").strip()
    return saida.split("\t")[0] if saida else None


def test_publica_guarda_5_e_reverte(exportado, remoto):
    dist, _ = exportado
    tags = [
        publicacao.publicar(dist, remoto, agora=datetime(2026, 10, d, 3, tzinfo=UTC))
        for d in range(1, 8)
    ]
    assert tags[-1] == "site-20261007-030000"
    publicadas = [p["tag"] for p in publicacao.listar(remoto)]
    assert publicadas == sorted(tags, reverse=True)[:5]  # só as 5 mais recentes
    no_ar = [p["tag"] for p in publicacao.listar(remoto) if p["no_ar"]]
    assert no_ar == ["site-20261007-030000"]

    # o site publicado tem o conteúdo e o .nojekyll, num commit sem histórico
    clone = Path(remoto).parent / "clone"
    subprocess.run(["git", "clone", "-q", "-b", "gh-pages", remoto, str(clone)], check=True)
    assert (clone / ".nojekyll").exists() and (clone / "dados" / "manifesto.json").exists()
    historico = subprocess.run(
        ["git", "-C", str(clone), "rev-list", "--count", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    assert historico == "1"

    # reverter sem argumento: volta para a anterior
    assert publicacao.reverter(remoto) == "site-20261006-030000"
    assert [p["tag"] for p in publicacao.listar(remoto) if p["no_ar"]] == ["site-20261006-030000"]
    # e de novo: a anterior à que está no ar agora
    assert publicacao.reverter(remoto) == "site-20261005-030000"
    # para uma tag específica
    assert publicacao.reverter(remoto, para="site-20261007-030000") == "site-20261007-030000"
    with pytest.raises(publicacao.ErroPublicacao, match="não existe"):
        publicacao.reverter(remoto, para="site-20200101-000000")


def test_publicacao_com_dados_faltando_nao_altera_o_site(exportado, remoto, tmp_path):
    dist, _ = exportado
    publicacao.publicar(dist, remoto, agora=datetime(2026, 10, 1, tzinfo=UTC))
    antes = _ramo(remoto)

    menor = tmp_path / "menor"
    shutil.copytree(dist, menor)
    lista = json.loads((menor / "dados" / "municipios.json").read_text())[:1]
    (menor / "dados" / "municipios.json").write_text(json.dumps(lista))
    m = json.loads((menor / "dados" / "manifesto.json").read_text())
    m["contagens"]["municipios"] = 1
    (menor / "dados" / "manifesto.json").write_text(json.dumps(m))

    with pytest.raises(publicacao.ErroPublicacao, match="municipios: 1 na nova versão, 2"):
        publicacao.publicar(menor, remoto, agora=datetime(2026, 10, 2, tzinfo=UTC))
    assert _ramo(remoto) == antes  # tudo ou nada: nada foi enviado
    assert len(publicacao.listar(remoto)) == 1


def test_token_nunca_aparece_em_mensagens():
    token = "github_pat_SEGREDO123"
    with pytest.raises(publicacao.ErroPublicacao) as erro:
        publicacao.listar("https://127.0.0.1:9/repo-inexistente.git", token)
    assert token not in str(erro.value)
    assert "***" in str(erro.value) or "127.0.0.1" in str(erro.value)
