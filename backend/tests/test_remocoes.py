"""Saídas de políticos só com aprovação (ADR-0026, decisão do Fabio, 21/11/2026).

Respostas reais gravadas (`fixtures/site_20261108`, ver o FONTE.md):

- versão publicada: recorte do site em vigor de 08/11 a 21/11/2026 (eleitos de Conchas,
  Jaú e Guaratinguetá e as entradas desses municípios em `municipios.json`);
- versão nova: os eleitos desses municípios que a regra de sempre
  (`tse.selecionar_eleitos`, como em `tse.coletar_eleitos`) tira do recorte do
  `consulta_cand_2024_SP.csv` do TSE de 21/11/2026, só com colunas públicas.
"""

import csv
import json
import shutil
import subprocess
from collections import defaultdict
from datetime import UTC, datetime

from test_site import banco as _banco
from test_site import exportado as _exportado
from test_site import remoto as _remoto

from conftest import FIXTURES
from rastro import publicacao, remocoes, site
from rastro.politicos import tse

banco, exportado, remoto = _banco, _exportado, _remoto  # fixtures de test_site

PUBLICADO = FIXTURES / "site_20261108"
TSE_21_11 = PUBLICADO / "tse_consulta_cand_2024_SP_recorte.csv"
CONCHAS, GUARATINGUETA, JAU = 3512308, 3518404, 3525300
UE_IBGE = {"63479": CONCHAS, "64696": GUARATINGUETA, "66079": JAU}  # código TSE -> IBGE
PAULO_NUNES = ("tse", "250002180907")  # prefeito, Conchas/SP
PEDRO_SANNINI = ("tse", "250001948460")  # vereador, Guaratinguetá/SP
SONIA_GUAJAJARA = ("camara", "220643")  # página politicos/15991.json
JAU_SAEM = {("tse", "250002243197"), ("tse", "250001959675")}
BASE = "site-20261108-140446"  # a publicação no ar quando as saídas foram aprovadas


def _eleitos_de_21_11() -> dict[int, list[dict]]:
    """{cod_ibge: itens} com os eleitos do arquivo do TSE de 21/11, pela regra de sempre."""
    with open(TSE_21_11, encoding="utf-8") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))
    cargos = tse.CARGOS[2024]
    saida: dict[int, list[dict]] = defaultdict(list)
    for ue, cargo_tse, eleitos, posteriores, _ in tse.selecionar_eleitos(linhas, cargos):
        if posteriores:  # suplementar sem resultado: o eleito anterior não vale
            eleitos = []
        saida[UE_IBGE[ue]] += [
            {
                "cargo": cargos[cargo_tse],
                "id_fonte": e["SQ_CANDIDATO"],
                "nome": e["NM_URNA_CANDIDATO"],
                "partido": e["SG_PARTIDO"],
                "situacao": e["DS_SIT_TOT_TURNO"],
            }
            for e in eleitos
        ]
    return saida


def _versao_de_21_11(tmp_path, cods=(CONCHAS, GUARATINGUETA, JAU)):
    """O recorte publicado com os eleitos dos municípios `cods` trocados pelos do arquivo
    do TSE de 21/11 (o id interno do banco, que a comparação não usa, fica de fora)."""
    novo = tmp_path / "novo"
    shutil.copytree(PUBLICADO, novo)
    eleitos = _eleitos_de_21_11()
    for cod in cods:
        arq = novo / "eleitos" / f"m-{cod}.json"
        d = json.loads(arq.read_text())
        d.pop("indices", None)
        d["itens"] = eleitos[cod]
        arq.write_text(json.dumps(d, ensure_ascii=False))
    return novo


def test_le_os_politicos_do_site_publicado():
    pol = remocoes.politicos_do_site(PUBLICADO)
    itens = sum(
        len(json.loads(a.read_text())["itens"]) for a in (PUBLICADO / "eleitos").glob("*.json")
    )
    assert len(pol) == itens + 1  # os eleitos e a página da deputada (a subpasta não conta)
    assert pol[SONIA_GUAJAJARA] == {
        "nome": "Sônia Guajajara",
        "cargo": "deputado_federal",
        "local": "SP",
    }
    assert pol[PAULO_NUNES] == {"nome": "PAULO NUNES", "cargo": "prefeito", "local": "Conchas/SP"}
    assert pol[PEDRO_SANNINI]["local"] == "Guaratinguetá/SP"


def test_arquivo_do_tse_de_21_11_da_as_quatro_saidas_e_as_tres_entradas(tmp_path):
    antes = remocoes.politicos_do_site(PUBLICADO)
    agora = remocoes.politicos_do_site(_versao_de_21_11(tmp_path))
    assert len(agora) == len(antes) - 1  # a queda que barrava a publicação desde 08/11
    assert set(antes) - set(agora) == {PAULO_NUNES, PEDRO_SANNINI, *JAU_SAEM}
    assert sorted(agora[k]["nome"] for k in set(agora) - set(antes)) == [
        "GUTO MACHADO",
        "MARCOS EVANGELISTA",
        "WILLIAN OLIVEIRA",
    ]


def test_lista_aprovada_tem_as_quatro_saidas_de_21_11():
    aprovadas = remocoes.carregar()
    publicados = remocoes.politicos_do_site(PUBLICADO)
    assert set(aprovadas) == {PAULO_NUNES, PEDRO_SANNINI, *JAU_SAEM}
    for chave, e in aprovadas.items():
        assert e["aprovado_por"] == "Fabio" and str(e["aprovado_em"]) == "2026-11-21"
        assert e["base"] == BASE
        assert publicados[chave]["nome"] == e["nome"]  # é quem estava publicado


def test_conchas_na_lista_passa_e_vai_para_o_resumo(tmp_path):
    novo = _versao_de_21_11(tmp_path, [CONCHAS])
    diff = remocoes.comparar(
        remocoes.politicos_do_site(PUBLICADO),
        remocoes.politicos_do_site(novo),
        remocoes.carregar(),
        BASE,
    )
    assert remocoes.problemas(diff) == []
    assert remocoes.resumo(diff) == [
        "Políticos: 0 entraram, 1 saíram",
        "  saiu (aprovada): PAULO NUNES (prefeito, Conchas/SP; tse 250002180907)",
    ]


def test_saida_fora_da_lista_barra(tmp_path):
    novo = _versao_de_21_11(tmp_path, [CONCHAS])
    diff = remocoes.comparar(
        remocoes.politicos_do_site(PUBLICADO), remocoes.politicos_do_site(novo), {}, BASE
    )
    assert remocoes.problemas(diff) == [
        "político saiu sem aprovação em remocoes_aprovadas.toml: "
        "PAULO NUNES (prefeito, Conchas/SP; tse 250002180907)"
    ]


def test_aprovacao_so_vale_na_base_em_que_foi_dada(tmp_path):
    """Com outra publicação no ar (ou sem tag conhecida), a mesma saída de Conchas conta
    como sem aprovação e barra."""
    novo = _versao_de_21_11(tmp_path, [CONCHAS])
    antes, agora = remocoes.politicos_do_site(PUBLICADO), remocoes.politicos_do_site(novo)
    for outra in ("site-20261201-043000", None):
        diff = remocoes.comparar(antes, agora, remocoes.carregar(), outra)
        assert remocoes.problemas(diff) == [
            "político saiu sem aprovação em remocoes_aprovadas.toml: "
            "PAULO NUNES (prefeito, Conchas/SP; tse 250002180907)"
        ]
        assert remocoes.resumo(diff)[1] == (
            "  saiu (SEM APROVAÇÃO): PAULO NUNES (prefeito, Conchas/SP; tse 250002180907)"
        )


def test_troca_com_contagem_igual_fora_da_lista_barra(tmp_path):
    """Guaratinguetá: sai um vereador, entra outro. A contagem não cai, e ainda assim a
    saída precisa estar na lista."""
    novo = _versao_de_21_11(tmp_path, [GUARATINGUETA])
    antes, agora = remocoes.politicos_do_site(PUBLICADO), remocoes.politicos_do_site(novo)
    assert len(agora) == len(antes)
    sem_pedro = {k: v for k, v in remocoes.carregar().items() if k != PEDRO_SANNINI}
    diff = remocoes.comparar(antes, agora, sem_pedro, BASE)
    assert remocoes.problemas(diff) == [
        "político saiu sem aprovação em remocoes_aprovadas.toml: "
        "PEDRO SANNINI (vereador, Guaratinguetá/SP; tse 250001948460)"
    ]
    # com a lista aprovada, passa; o resumo mostra quem entrou e quem saiu
    diff = remocoes.comparar(antes, agora, remocoes.carregar(), BASE)
    assert remocoes.problemas(diff) == []
    assert remocoes.resumo(diff) == [
        "Políticos: 1 entraram, 1 saíram",
        "  entrou: MARCOS EVANGELISTA (vereador, Guaratinguetá/SP; tse 250001948465)",
        "  saiu (aprovada): PEDRO SANNINI (vereador, Guaratinguetá/SP; tse 250001948460)",
    ]


def test_versao_de_21_11_inteira_passa_com_a_lista(tmp_path):
    novo = _versao_de_21_11(tmp_path)
    diff = remocoes.comparar(
        remocoes.politicos_do_site(PUBLICADO),
        remocoes.politicos_do_site(novo),
        remocoes.carregar(),
        BASE,
    )
    assert remocoes.problemas(diff) == []
    assert len(diff["entraram"]) == 3 and len(diff["sairam"]) == 4


def test_verificar_compara_um_a_um_e_nao_pela_contagem(exportado, monkeypatch):
    """Com os políticos publicados, a contagem de políticos dá lugar à comparação um a um.
    O site exportado não tem Paulo Nunes; o publicado tinha."""
    dist, manifesto = exportado
    dados = dist / "dados"
    agora = remocoes.politicos_do_site(dados)
    publicados = {**agora, PAULO_NUNES: remocoes.politicos_do_site(PUBLICADO)[PAULO_NUNES]}
    anterior = {
        **manifesto,
        "contagens": {**manifesto["contagens"], "politicos": len(publicados)},
    }
    assert site.verificar(dados, anterior, publicados, BASE) == []
    queda = f"politicos: {len(agora)} na nova versão, {len(publicados)} na publicada"
    # sem a comparação um a um (sem os políticos publicados), vale a contagem, como antes
    assert queda in site.verificar(dados, anterior)
    # se os políticos lidos do site publicado não somam a contagem do manifesto dele, a
    # contagem também vale
    maior = {**anterior, "contagens": {**anterior["contagens"], "politicos": len(publicados) + 1}}
    assert site.verificar(dados, maior, publicados, BASE) == [
        f"politicos: {len(agora)} na nova versão, {len(publicados) + 1} na publicada"
    ]
    # fora da lista, barra
    vazia = dist.parent / "vazia.toml"
    vazia.write_text("")
    monkeypatch.setattr(remocoes, "ARQUIVO", vazia)
    assert site.verificar(dados, anterior, publicados, BASE) == [
        "político saiu sem aprovação em remocoes_aprovadas.toml: "
        "PAULO NUNES (prefeito, Conchas/SP; tse 250002180907)"
    ]


def test_dispensas_continuam_e_sao_nomeadas(exportado):
    """Trava alterada de propósito: a saída não barra, e o motivo fica disponível para o
    resumo da execução."""
    dist, manifesto = exportado
    dados = dist / "dados"
    agora = remocoes.politicos_do_site(dados)
    publicados = {**agora, PAULO_NUNES: remocoes.politicos_do_site(PUBLICADO)[PAULO_NUNES]}
    travas = {**manifesto["travas"]}
    chave = next(iter(travas))
    travas[chave] = not travas[chave]
    anterior = {
        **manifesto,
        "travas": travas,
        "contagens": {**manifesto["contagens"], "politicos": len(publicados)},
    }
    assert site.dispensa_politicos(manifesto, anterior) == (
        "travas de publicação diferentes das da versão no ar (mudança de propósito)"
    )
    assert site.verificar(dados, anterior, publicados, None) == []
    # sem a dispensa, a mesma saída sem base conhecida barra
    assert site.verificar(dados, {**anterior, "travas": manifesto["travas"]}, publicados, None)


def test_le_os_politicos_do_gh_pages(remoto, tmp_path):
    """`_politicos_publicados` lê do branch publicado os mesmos políticos que estão nos
    arquivos: o recorte real de 08/11 posto como `dados/` num gh-pages local."""
    trabalho = tmp_path / "trabalho"
    shutil.copytree(PUBLICADO, trabalho / "dados")
    (trabalho / "dados" / TSE_21_11.name).unlink()  # não faz parte do site
    for args in (
        ["init", "-q", "-b", "gh-pages"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "0"],
        ["add", "-A"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "site"],
        ["tag", BASE],
        ["push", "-q", remoto, "gh-pages", BASE],
    ):
        subprocess.run(["git", *args], cwd=trabalho, check=True)
    git = publicacao.Git(remoto, None)
    try:
        git("fetch", "-q", "--depth=1", "origin", "gh-pages")
        lidos = publicacao._politicos_publicados(git)
        base = publicacao._base_no_ar(git)
    finally:
        git.fechar()
    assert lidos == remocoes.politicos_do_site(PUBLICADO)
    assert lidos[PAULO_NUNES]["local"] == "Conchas/SP"
    # as páginas de deputados e senadores também (em 22/11 elas ficavam de fora: o
    # `git ls-tree` não aceita pathspec com glob)
    assert SONIA_GUAJAJARA in lidos
    assert base == BASE


def test_publicacao_mostra_o_resumo_mesmo_quando_passa(exportado, remoto, capsys):
    dist, _ = exportado
    publicacao.publicar(dist, remoto, agora=datetime(2026, 11, 1, tzinfo=UTC))
    capsys.readouterr()
    publicacao.publicar(dist, remoto, agora=datetime(2026, 11, 2, tzinfo=UTC), simular=True)
    saida = capsys.readouterr().out
    assert "Publicação no ar (base da comparação): site-20261101-000000" in saida
    assert "Políticos: 0 entraram, 0 saíram" in saida
    assert "Dispensa usada" not in saida
    # trava alterada de propósito: o resumo diz numa linha que a dispensa foi usada
    m = json.loads((dist / "dados" / "manifesto.json").read_text())
    chave = next(iter(m["travas"]))
    m["travas"][chave] = not m["travas"][chave]
    (dist / "dados" / "manifesto.json").write_text(json.dumps(m))
    publicacao.publicar(dist, remoto, agora=datetime(2026, 11, 3, tzinfo=UTC), simular=True)
    assert (
        "Dispensa usada: travas de publicação diferentes das da versão no ar (mudança de "
        "propósito); as saídas acima não barram a publicação"
    ) in capsys.readouterr().out
