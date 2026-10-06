from datetime import UTC, datetime
from decimal import Decimal as D

import pytest

from rastro import indicadores as ind
from rastro.models import ContaDemonstrativo, DemonstrativoSiconfi

COD = 3500105  # Adamantina/SP, valores reais do exercício de 2025


def _demonstrativo(
    session, demonstrativo, periodicidade, periodo, poder, instituicao, contas, exercicio=2025
):
    d = DemonstrativoSiconfi(
        cod_ibge=COD, exercicio=exercicio, demonstrativo=demonstrativo, periodicidade=periodicidade,
        periodo=periodo, poder=poder, instituicao=instituicao,
        data_status=datetime(2026, 3, 20, tzinfo=UTC), linhas=len(contas),
        contas=[
            ContaDemonstrativo(
                anexo=anexo, rotulo="Padrão", coluna=coluna, cod_conta=cod, conta=cod, valor=v
            )
            for anexo, cod, coluna, v in contas
        ],
    )  # fmt: skip
    session.add(d)
    return d


def _pessoal(pct, alerta, prud, maximo, valor="1", rcl="314310321.59"):
    a, c = "RGF-Anexo 01", "% sobre a RCL Ajustada"
    return [
        (a, "DespesaComPessoalTotal", "Valor", D(valor)),
        (a, "DespesaComPessoalTotal", c, D(pct)),
        (a, "ReceitaCorrenteLiquidaAjustada", "Valor", D(rcl)),
        (a, "LimiteDeAlertaDespesaComPessoalTotal", c, D(alerta)),
        (a, "LimitePrudencialDespesaComPessoalTotal", c, D(prud)),
        (a, "LimiteMaximoDespesaComPessoalTotal", c, D(maximo)),
    ]


@pytest.fixture
def adamantina(session):
    a2, col = "RGF-Anexo 02", "Até o 2º Semestre"
    divida = [
        (a2, "DividaConsolidadaLiquida", col, D("-68925467.28")),
        (a2, "DividaConsolidadaLiquida", "Até o 1º Semestre", D("-97218479.83")),
        (a2, "ReceitaCorrenteLiquidaAjustadaParaCalculoDosLimitesDeEndividamento", col,
         D("314310321.59")),
        (a2, "LimiteDeAlerta", col, D("339455147.32")),
        (a2, "LimiteDefinidoPorResolucaoDoSenadoFederal", col, D("377172385.91")),
    ]  # fmt: skip
    # semestre 1 existe, mas os indicadores devem usar o último período (semestre 2)
    _demonstrativo(
        session, "RGF Simplificado", "S", 1, "E", "Prefeitura",
        _pessoal("99", "48.6", "51.3", "54"),
    )  # fmt: skip
    _demonstrativo(
        session, "RGF Simplificado", "S", 2, "E", "Prefeitura",
        _pessoal("50.82", "48.6", "51.3", "54", valor="159725438.63") + divida,
    )  # fmt: skip
    _demonstrativo(
        session, "RGF Simplificado", "S", 2, "L", "Câmara", _pessoal("0.9", "5.4", "5.7", "6")
    )
    a1 = "RREO-Anexo 01"
    _demonstrativo(
        session, "RREO Simplificado", "B", 6, None, "Prefeitura",
        [
            (a1, "TotalReceitas", "PREVISÃO ATUALIZADA (a)", D("334541301.62")),
            (a1, "TotalReceitas", "Até o Bimestre (c)", D("319343024.46")),
            (a1, "TotalDespesas", "DOTAÇÃO ATUALIZADA (e)", D("345944369.2")),
            (a1, "TotalDespesas", "DESPESAS EMPENHADAS ATÉ O BIMESTRE (f)", D("319695009.96")),
            (a1, "TotalDespesas", "DESPESAS LIQUIDADAS ATÉ O BIMESTRE (h)", D("310704404.53")),
            (a1, "TotalDespesas", "DESPESAS PAGAS ATÉ O BIMESTRE (j)", D("306270685")),
            (a1, "SuperavitFinanceiro", "Até o Bimestre (c)", D("20228071")),
        ],
    )  # fmt: skip
    session.commit()


def test_pessoal_usa_ultimo_periodo_e_classifica(session, adamantina):
    p = ind.pessoal(session, COD, 2025)
    assert [(x["poder"], x["periodo"], x["percentual"], x["situacao"]) for x in p] == [
        ("E", 2, D("50.82"), "acima_alerta"),
        ("L", 2, D("0.9"), "regular"),
    ]
    assert p[0]["nome_poder"] == "Executivo"


@pytest.mark.parametrize(
    ("pct", "esperado"),
    [("48.6", "regular"), ("48.61", "acima_alerta"), ("51.31", "acima_prudencial"),
     ("54.01", "acima_maximo")],
)  # fmt: skip
def test_situacao_segue_limites_da_lrf(pct, esperado):
    # a LRF fala em "exceder"/"ultrapassar": atingir o limite exato ainda é regular
    assert ind._situacao(D(pct), D("48.6"), D("51.3"), D("54")) == esperado


def test_divida_calcula_percentuais_dos_limites(session, adamantina):
    d = ind.divida(session, COD, 2025)
    assert d["percentual"] == D("-21.93")  # DCL negativa: caixa maior que a dívida
    assert d["limite_maximo"] == D("120.00")  # 1,2 x RCL (Resolução do Senado 40/2001)
    assert d["limite_alerta"] == D("108.00")
    assert d["situacao"] == "regular"


def test_execucao_e_resultado_orcamentario(session, adamantina):
    e = ind.execucao(session, COD, 2025)
    assert e["periodo"] == 6
    assert e["resultado"] == D("-351985.50")  # bate com o "Déficit" declarado no RREO
    assert e["despesa_paga"] == D("306270685")


def test_ente_sem_dados(session):
    assert ind.indicadores(session, 1234567, 2025) == {
        "cod_ibge": 1234567, "exercicio": 2025, "pessoal": [], "divida": None, "execucao": None,
    }  # fmt: skip


def test_serie_traz_um_item_por_exercicio_em_ordem(session, adamantina):
    _demonstrativo(
        session, "RGF Simplificado", "S", 2, "E", "Prefeitura",
        _pessoal("47.1", "48.6", "51.3", "54"), exercicio=2024,
    )  # fmt: skip
    session.commit()
    serie = ind.serie(session, COD)
    assert [x["exercicio"] for x in serie] == [2024, 2025]
    assert serie[0]["pessoal"][0]["percentual"] == D("47.1")
    assert serie[0]["execucao"] is None  # 2024 sem RREO: ausente, não zero
