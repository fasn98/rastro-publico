"""Redação LGPD no arquivo de respostas brutas e varredura de dados pessoais no banco."""

import gzip
import io
import json
import re
import zipfile

import pytest
import respx
from sqlalchemy import func, select, text

from conftest import FIXTURES
from rastro.coletores.arquivo import ArquivoBruto, Redacao, com_redacao, ler_payload, sha256
from rastro.coletores.base import get_json_com_origem, novo_cliente
from rastro.coletores.redacao import redator_csv, redator_json, redigir_arquivadas
from rastro.models import PayloadBruto, RespostaBruta
from rastro.politicos import camara, lgpd, senado

POL = FIXTURES / "politicos"
JSON = {"content-type": "application/json"}
EMAIL = re.compile(rb"[\w.+-]+@[\w-]+\.[\w.]+")


@pytest.fixture
def cliente(engine):
    with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
        yield c


def _payload(session, r: RespostaBruta) -> bytes:
    return ler_payload(session.get(PayloadBruto, r.sha256))


def _conta(session, modelo):
    return session.scalar(select(func.count()).select_from(modelo))


@respx.mock
def test_redator_grava_versao_sem_campos_e_hash_do_original(session, cliente):
    original = (POL / "senado_senadores_atual.json").read_bytes()
    assert b"EmailParlamentar" in original and EMAIL.search(original)
    url = f"{senado.API}/senador/lista/atual.json"
    respx.get(url).respond(content=original, headers=JSON)
    dados, rid = get_json_com_origem(cliente, url, redator=lgpd.SENADO_LISTA)
    # o coletor recebe o conteúdo completo; só o arquivo é redigido
    assert "EmailParlamentar" in json.dumps(dados)
    r = session.get(RespostaBruta, rid)
    gravado = _payload(session, r)
    assert (r.sha256_original, r.tamanho_original) == (sha256(original), len(original))
    assert r.sha256 == sha256(gravado) != r.sha256_original
    assert r.campos_removidos == ["EmailParlamentar"]
    assert "EmailParlamentar" in r.redacao
    assert b"EmailParlamentar" not in gravado and not EMAIL.search(gravado)
    # o original não foi guardado em lugar nenhum
    assert session.get(PayloadBruto, sha256(original)) is None
    # o resto do conteúdo é o mesmo
    parlamentares = json.loads(gravado)["ListaParlamentarEmExercicio"]["Parlamentares"]
    antes = json.loads(original)["ListaParlamentarEmExercicio"]["Parlamentares"]
    assert len(parlamentares["Parlamentar"]) == len(antes["Parlamentar"])


@respx.mock
def test_redator_que_falha_nao_grava_nada(session, cliente):
    respx.get("https://exemplo.gov.br/x").respond(content=b"{}", headers=JSON)

    def quebra(_):
        raise ValueError("layout inesperado")

    with pytest.raises(ValueError):
        cliente.get("https://exemplo.gov.br/x", extensions=com_redacao(quebra))
    assert _conta(session, RespostaBruta) == _conta(session, PayloadBruto) == 0


@respx.mock
def test_resposta_de_erro_nao_passa_pelo_redator(session, cliente):
    corpo = (POL / "transparencia_emendas_sem_chave.json").read_bytes()
    respx.get("https://api.portaldatransparencia.gov.br/api-de-dados/emendas").respond(
        401, content=corpo
    )
    cliente.get(
        "https://api.portaldatransparencia.gov.br/api-de-dados/emendas",
        extensions=com_redacao(lambda b: Redacao(b"", ["tudo"])),
    )
    r = session.scalars(select(RespostaBruta)).one()
    assert r.sha256_original is None and _payload(session, r) == corpo


def test_redator_csv_em_zip_remove_colunas_e_filtra_linhas():
    # ZIP montado no teste com o CSV real da Câmara dentro (dois membros, como no TSE)
    csv_real = (POL / "camara_eventosPresencaDeputados_2025_amostra.csv").read_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("presencas_SP.csv", csv_real)
        z.writestr("presencas_BRASIL.csv", csv_real)
    redator = redator_csv(
        ["uriDeputado", "uriEvento"],
        filtro=lambda linha: linha["idDeputado"] == "204534",
        descricao_filtro="só idDeputado=204534",
        membro_zip="*_SP.csv",
    )
    red = redator(buf.getvalue())
    linhas = red.conteudo.decode().strip().split("\n")
    assert linhas[0] == '"idEvento";"dataHoraInicio";"idDeputado"'
    # as duas linhas de 204534 no CSV real, sem as colunas de URI
    esperado = ['"75098";"2025-04-08T14:56:55";"204534"', '"75320";"2025-03-19T11:06:43";"204534"']
    assert linhas[1:] == esperado
    assert len(linhas) == 3
    assert red.campos_removidos == ["uriEvento", "uriDeputado"]
    assert "membro presencas_SP.csv" in red.descricao and "2 de " in red.descricao


def test_redator_csv_falha_se_coluna_esperada_nao_existe():
    csv_real = (POL / "camara_eventosPresencaDeputados_2025_amostra.csv").read_bytes()
    with pytest.raises(ValueError, match="NR_CPF_CANDIDATO"):
        redator_csv(["NR_CPF_CANDIDATO"])(csv_real)


def test_redator_json_remove_em_qualquer_nivel():
    original = (POL / "camara_deputados_sp_atual.json").read_bytes()
    red = redator_json({"email"})(original)
    assert red.campos_removidos == ["email"]
    dados = json.loads(red.conteudo)
    assert len(dados["dados"]) == 70 and all("email" not in d for d in dados["dados"])


@respx.mock
def test_redigir_respostas_ja_arquivadas(session, cliente):
    original = (POL / "senado_senadores_atual.json").read_bytes()
    url = f"{senado.API}/senador/lista/atual.json"
    respx.get(url).respond(content=original, headers=JSON)
    get_json_com_origem(cliente, url)  # coleta antiga, sem redação
    assert session.get(PayloadBruto, sha256(original)) is not None
    assert redigir_arquivadas(session, lgpd.REGRAS) == 1
    assert redigir_arquivadas(session, lgpd.REGRAS) == 0  # idempotente
    r = session.scalars(select(RespostaBruta)).one()
    session.refresh(r)
    assert r.sha256_original == sha256(original)
    assert b"EmailParlamentar" not in _payload(session, r)
    assert session.get(PayloadBruto, sha256(original)) is None  # original apagado


# ------------------------------------------------------------------ varredura


PROIBIDOS = [
    rb"\bcpf\b",
    rb"NR_CPF",
    rb"dataNascimento",
    rb"DataNascimento",
    rb"DT_NASCIMENTO",
    rb"TITULO_ELEITORAL",
    rb"EMAIL",
]


def _despejo(session) -> list[tuple[str, bytes]]:
    """Todo o conteúdo do banco: cada linha de cada tabela e cada payload descomprimido."""
    saida = []
    tabelas = session.execute(
        text("select tablename from pg_tables where schemaname = 'public'")
    ).scalars()
    for t in tabelas:
        for linha in session.execute(text(f'select row_to_json(x)::text from "{t}" x')).scalars():
            saida.append((t, linha.encode()))
    for p in session.scalars(select(PayloadBruto)):
        saida.append((f"payload {p.sha256[:12]}", gzip.decompress(p.conteudo)))
    return saida


@respx.mock
def test_nenhum_dado_pessoal_no_banco_nem_no_arquivo_bruto(session, cliente):
    from test_politicos import _mock_camara, _mock_senado

    _mock_camara()
    _mock_senado()
    mapa = camara.coletar_deputados(session, cliente, "SP")
    camara.coletar_proposicoes(session, cliente, 204534, mapa[204534], 2025)
    camara.coletar_votos(session, cliente, 2025, mapa)
    camara.coletar_presencas(session, cliente, 2025, mapa)
    pid = senado.coletar_senadores(session, cliente, "SP")["6009"]
    senado.coletar_materias(session, cliente, "6009", pid, 2025)
    senado.coletar_votacoes(session, cliente, "6009", pid, 2025)
    senado.coletar_comissoes(session, cliente, "6009", pid)

    despejo = _despejo(session)
    assert any(origem.startswith("payload") for origem, _ in despejo)
    for origem, conteudo in despejo:
        assert not EMAIL.search(conteudo), (origem, EMAIL.search(conteudo)[0])
        if not origem.startswith("payload"):
            continue  # nas tabelas, `campos_removidos` cita os nomes dos campos (sem valores)
        for padrao in PROIBIDOS:
            assert not re.search(padrao, conteudo, re.I), (origem, padrao)
