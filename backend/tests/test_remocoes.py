"""Saídas de políticos só com aprovação (ADR-0026, decisão do Fabio, 21/11/2026).

Versão publicada: recorte real do site em vigor de 08/11 a 21/11/2026
(`fixtures/site_20261108`, ver o FONTE.md). Versão nova: a mesma, com as mudanças que o
arquivo do TSE de 21/11/2026 traz para Conchas, Jaú e Guaratinguetá (SQ_CANDIDATO, nome
de urna, partido e situação lidos do arquivo; os eleitos que entram não têm o id interno
do banco, que a comparação não usa).
"""

import json
import shutil
from datetime import UTC, datetime

from test_site import banco as _banco
from test_site import exportado as _exportado
from test_site import remoto as _remoto

from conftest import FIXTURES
from rastro import publicacao, remocoes, site

banco, exportado, remoto = _banco, _exportado, _remoto  # fixtures de test_site

PUBLICADO = FIXTURES / "site_20261108"
PAULO_NUNES = ("tse", "250002180907")  # prefeito, Conchas/SP
PEDRO_SANNINI = ("tse", "250001948460")  # vereador, Guaratinguetá/SP
# (SQ_CANDIDATO, nome de urna, partido), arquivo do TSE de 21/11/2026, "ELEITO POR MÉDIA"
MARCOS_EVANGELISTA = ("250001948465", "MARCOS EVANGELISTA", "PL")  # Guaratinguetá
JAU_ENTRAM = [
    ("250001903239", "WILLIAN OLIVEIRA", "AVANTE"),
    ("250002243398", "GUTO MACHADO", "PT"),
]
JAU_SAEM = {"250002243197", "250001959675"}


def _copia(tmp_path, nome="novo"):
    destino = tmp_path / nome
    shutil.copytree(PUBLICADO, destino)
    return destino


def _mudar(dados, cod: int, saem: set[str], entram: list[tuple[str, str, str]]):
    """Tira e põe vereadores no arquivo de eleitos do município, no formato do site."""
    arq = dados / "eleitos" / f"m-{cod}.json"
    d = json.loads(arq.read_text())
    d["itens"] = [i for i in d["itens"] if i["id_fonte"] not in saem]
    for id_fonte, nome, partido in entram:
        cargos, situacoes = d["indices"]["cargo"], d["indices"]["situacao"]
        d["itens"].append(
            {
                "cargo": cargos.index("vereador"),
                "id_fonte": id_fonte,
                "nome": nome,
                "partido": partido,
                "situacao": situacoes.index("ELEITO POR MÉDIA"),
            }
        )
    arq.write_text(json.dumps(d, ensure_ascii=False))


def _versao_de_21_11(tmp_path):
    """O recorte com as quatro saídas e as três entradas do arquivo do TSE de 21/11."""
    novo = _copia(tmp_path)
    _mudar(novo, 3512308, {PAULO_NUNES[1]}, [])
    _mudar(novo, 3525300, JAU_SAEM, JAU_ENTRAM)
    _mudar(novo, 3518404, {PEDRO_SANNINI[1]}, [MARCOS_EVANGELISTA])
    return novo


def test_le_os_politicos_do_site_publicado():
    pol = remocoes.politicos_do_site(PUBLICADO)
    itens = sum(
        len(json.loads(a.read_text())["itens"]) for a in (PUBLICADO / "eleitos").glob("*.json")
    )
    assert len(pol) == itens
    assert pol[PAULO_NUNES] == {"nome": "PAULO NUNES", "cargo": "prefeito", "local": "Conchas/SP"}
    assert pol[PEDRO_SANNINI]["local"] == "Guaratinguetá/SP"


def test_lista_aprovada_tem_as_quatro_saidas_de_21_11():
    aprovadas = remocoes.carregar()
    publicados = remocoes.politicos_do_site(PUBLICADO)
    assert set(aprovadas) == {
        PAULO_NUNES,
        PEDRO_SANNINI,
        *{("tse", i) for i in JAU_SAEM},
    }
    for chave, e in aprovadas.items():
        assert e["aprovado_por"] == "Fabio" and str(e["aprovado_em"]) == "2026-11-21"
        assert publicados[chave]["nome"] == e["nome"]  # é quem estava publicado


def test_conchas_na_lista_passa_e_vai_para_o_resumo(tmp_path):
    novo = _copia(tmp_path)
    _mudar(novo, 3512308, {PAULO_NUNES[1]}, [])
    diff = remocoes.comparar(
        remocoes.politicos_do_site(PUBLICADO),
        remocoes.politicos_do_site(novo),
        remocoes.carregar(),
    )
    assert remocoes.problemas(diff) == []
    assert remocoes.resumo(diff) == [
        "Políticos: 0 entraram, 1 saíram",
        "  saiu (aprovada): PAULO NUNES (prefeito, Conchas/SP; tse 250002180907)",
    ]


def test_saida_fora_da_lista_barra(tmp_path):
    novo = _copia(tmp_path)
    _mudar(novo, 3512308, {PAULO_NUNES[1]}, [])
    diff = remocoes.comparar(
        remocoes.politicos_do_site(PUBLICADO), remocoes.politicos_do_site(novo), {}
    )
    assert remocoes.problemas(diff) == [
        "político saiu sem aprovação em remocoes_aprovadas.toml: "
        "PAULO NUNES (prefeito, Conchas/SP; tse 250002180907)"
    ]


def test_troca_com_contagem_igual_fora_da_lista_barra(tmp_path):
    """Guaratinguetá: sai um vereador, entra outro. A contagem não cai, e ainda assim a
    saída precisa estar na lista."""
    novo = _copia(tmp_path)
    _mudar(novo, 3518404, {PEDRO_SANNINI[1]}, [MARCOS_EVANGELISTA])
    antes, agora = remocoes.politicos_do_site(PUBLICADO), remocoes.politicos_do_site(novo)
    assert len(agora) == len(antes)
    sem_pedro = {k: v for k, v in remocoes.carregar().items() if k != PEDRO_SANNINI}
    diff = remocoes.comparar(antes, agora, sem_pedro)
    assert remocoes.problemas(diff) == [
        "político saiu sem aprovação em remocoes_aprovadas.toml: "
        "PEDRO SANNINI (vereador, Guaratinguetá/SP; tse 250001948460)"
    ]
    # com a lista aprovada, passa; o resumo mostra quem entrou e quem saiu
    diff = remocoes.comparar(antes, agora, remocoes.carregar())
    assert remocoes.problemas(diff) == []
    assert remocoes.resumo(diff) == [
        "Políticos: 1 entraram, 1 saíram",
        "  entrou: MARCOS EVANGELISTA (vereador, Guaratinguetá/SP; tse 250001948465)",
        "  saiu (aprovada): PEDRO SANNINI (vereador, Guaratinguetá/SP; tse 250001948460)",
    ]


def test_versao_de_21_11_inteira_passa_com_a_lista(tmp_path):
    novo = _versao_de_21_11(tmp_path)
    antes, agora = remocoes.politicos_do_site(PUBLICADO), remocoes.politicos_do_site(novo)
    assert len(agora) == len(antes) - 1  # a queda que barrava a publicação desde 08/11
    diff = remocoes.comparar(antes, agora, remocoes.carregar())
    assert remocoes.problemas(diff) == []
    assert len(diff["entraram"]) == 3 and len(diff["sairam"]) == 4


def test_verificar_compara_um_a_um_e_nao_pela_contagem(exportado, monkeypatch):
    """Com os políticos publicados, a contagem de políticos não é mais conferida: vale a
    comparação um a um. O site exportado não tem Paulo Nunes; o publicado tinha."""
    dist, manifesto = exportado
    dados = dist / "dados"
    agora = remocoes.politicos_do_site(dados)
    publicados = {**agora, PAULO_NUNES: remocoes.politicos_do_site(PUBLICADO)[PAULO_NUNES]}
    anterior = {
        **manifesto,
        "contagens": {**manifesto["contagens"], "politicos": len(publicados)},
    }
    assert site.verificar(dados, anterior, publicados) == []
    # sem a comparação um a um (sem os políticos publicados), vale a contagem, como antes
    assert f"politicos: {len(agora)} na nova versão, {len(publicados)} na publicada" in (
        site.verificar(dados, anterior)
    )
    # fora da lista, barra
    vazia = dist.parent / "vazia.toml"
    vazia.write_text("")
    monkeypatch.setattr(remocoes, "ARQUIVO", vazia)
    assert site.verificar(dados, anterior, publicados) == [
        "político saiu sem aprovação em remocoes_aprovadas.toml: "
        "PAULO NUNES (prefeito, Conchas/SP; tse 250002180907)"
    ]


def test_publicacao_le_os_politicos_publicados_e_mostra_o_resumo(exportado, remoto, capsys):
    dist, _ = exportado
    publicacao.publicar(dist, remoto, agora=datetime(2026, 11, 1, tzinfo=UTC))
    git = publicacao.Git(remoto, None)
    try:
        assert publicacao._manifesto_publicado(git) is not None
        assert publicacao._politicos_publicados(git) == remocoes.politicos_do_site(dist / "dados")
    finally:
        git.fechar()
    capsys.readouterr()
    publicacao.publicar(dist, remoto, agora=datetime(2026, 11, 2, tzinfo=UTC), simular=True)
    assert "Políticos: 0 entraram, 0 saíram" in capsys.readouterr().out
