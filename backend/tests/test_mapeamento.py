"""Armazenamento enxuto: só as linhas do mapeamento vão para conta_demonstrativo,
o arquivo bruto guarda tudo e qualquer linha pode ser reconstruída a partir dele."""

import json
from decimal import Decimal as D

import pytest
import respx
from sqlalchemy import func, select

from conftest import carregar
from rastro import indicadores as ind
from rastro import mapeamento as mp
from rastro.coletores import siconfi_demonstrativos as sd
from rastro.coletores.arquivo import ArquivoBruto
from rastro.coletores.base import novo_cliente
from rastro.models import (
    ContaDemonstrativo,
    DemonstrativoResposta,
    DemonstrativoSiconfi,
    EnteSiconfi,
)

ADAMANTINA = dict(cod_ibge=3500105, nome="Adamantina", esfera="M", uf="SP", regiao="SE",
                  capital=False, populacao=35673, exercicio=2026)  # fmt: skip


@pytest.mark.parametrize(
    ("linha", "aceita"),
    [
        ({"anexo": "RGF-Anexo 01", "cod_conta": "DespesaComPessoalTotal",
          "coluna": "Valor"}, True),
        ({"anexo": "RGF-Anexo 01", "cod_conta": "DespesaComPessoalTotal",
          "coluna": "<MR-1>"}, False),
        ({"anexo": "RGF-Anexo 01", "cod_conta": "DespesaComPessoalBruta",
          "coluna": "Valor"}, False),
        # coluna por prefixo ("Até o *")
        ({"anexo": "RGF-Anexo 02", "cod_conta": "DividaConsolidadaLiquida",
          "coluna": "Até o 2º Semestre"}, True),
        # conta por texto: função sim, subfunção não
        ({"anexo": "RREO-Anexo 02", "cod_conta": "RREO2TotalDespesas", "conta": "Legislativa",
          "rotulo": "Total das Despesas Exceto Intra-Orçamentárias",
          "coluna": "DESPESAS EMPENHADAS ATÉ O BIMESTRE (b)"}, True),
        ({"anexo": "RREO-Anexo 02", "cod_conta": "RREO2TotalDespesas", "conta": "Ação Legislativa",
          "rotulo": "Total das Despesas Exceto Intra-Orçamentárias",
          "coluna": "DESPESAS EMPENHADAS ATÉ O BIMESTRE (b)"}, False),
        # conta por prefixo (RGF Anexo 5)
        ({"anexo": "RGF-Anexo 05", "cod_conta": "DisponibilidadeDeCaixaLiquidaAposRP",
          "conta": "TOTAL DOS RECURSOS NÃO VINCULADOS (I)", "coluna": "x"}, True),
    ],
)  # fmt: skip
def test_regras_do_mapeamento(linha, aceita):
    assert mp.padrao().aceita(linha) is aceita


@pytest.fixture
def coletado(session, engine):
    ente = EnteSiconfi(**ADAMANTINA)
    session.add(ente)
    session.commit()
    with respx.mock:
        respx.get(sd.URL_EXTRATO).respond(json=carregar("adamantina_2025_extrato.json"))
        respx.get(sd.URL_RREO).respond(json=carregar("adamantina_2025_rreo6.json"))
        for p in "EL":
            respx.get(sd.URL_RGF, params__contains={"co_poder": p}).respond(
                json=carregar(f"adamantina_2025_rgf2_{p}.json")
            )
        with novo_cliente(req_por_segundo=0, arquivo=ArquivoBruto(engine)) as c:
            sd.coletar_ente(session, c, ente, 2025)
    return ente


def test_grava_so_o_mapeamento_e_liga_ao_bruto(session, coletado):
    gravadas = session.scalar(select(func.count()).select_from(ContaDemonstrativo))
    da_api = session.scalar(select(func.sum(DemonstrativoSiconfi.linhas)))
    assert 0 < gravadas < da_api
    m = mp.padrao()
    for c in session.scalars(select(ContaDemonstrativo)):
        assert m.aceita(c.__dict__) and c.resposta_id is not None
    # todo demonstrativo aponta para as respostas brutas de onde veio
    sem_origem = session.scalar(
        select(func.count())
        .select_from(DemonstrativoSiconfi)
        .where(~DemonstrativoSiconfi.respostas.any())
    )
    assert sem_origem == 0
    # e os indicadores aprovados continuam saindo iguais
    assert ind.autonomia(session, 3500105, 2025)["razao"] == D("4.3073")
    assert ind.liquidez(session, 3500105, 2025)["percentual"] == D("21.9289")
    assert ind.pessoal(session, 3500105, 2025)[0]["percentual"] == D("50.82")
    assert ind.divida(session, 3500105, 2025)["percentual"] == D("-21.93")
    assert ind.execucao(session, 3500105, 2025)["resultado"] == D("-351985.50")


def test_reconstroi_linha_fora_do_mapeamento(session, coletado):
    from rastro import reconstrucao as rc

    nao_gravada = dict(anexo="RGF-Anexo 01", cod_conta="DespesaComPessoalBruta")
    assert (
        session.scalar(
            select(func.count()).select_from(ContaDemonstrativo).filter_by(**nao_gravada)
        )
        == 0
    )

    filtro = rc.Filtro(anexo="RGF-Anexo 01", cod_conta=["DespesaComPessoalBruta"])
    linhas = list(rc.reconstruir(session, filtro))
    esperado = [
        i for p in "EL" for i in carregar(f"adamantina_2025_rgf2_{p}.json")["items"]
        if i["cod_conta"] == "DespesaComPessoalBruta"
    ]  # fmt: skip
    # semestres 1 e 2 vieram do mesmo fixture: cada linha aparece nos dois períodos
    assert len(linhas) == 2 * len(esperado)
    assert all(li.resposta_id for li in linhas)
    valores = sorted(str(li.valor) for li in linhas)
    assert valores == sorted(str(i["valor"]) for i in esperado * 2)

    # --gravar insere com origem, e repetir não duplica
    assert rc.gravar(session, linhas) == len(linhas)
    assert rc.gravar(session, linhas) == 0
    origem = session.scalars(select(ContaDemonstrativo.resposta_id).filter_by(**nao_gravada)).all()
    assert len(origem) == len(linhas) and all(origem)


def test_aplicar_mapeamento_poda_e_reconstroi(session, coletado, tmp_path):
    from rastro import reconstrucao as rc

    # um mapeamento novo, que passa a querer também a despesa bruta com pessoal
    texto = mp.ARQUIVO_PADRAO.read_text() + (
        "  - anexo: RGF-Anexo 01\n    cod_conta: [DespesaComPessoalBruta]\n"
    )
    arq = tmp_path / "m.yaml"
    arq.write_text(texto)
    novo = mp.carregar(arq)
    antes = session.scalar(select(func.count()).select_from(ContaDemonstrativo))
    resumo = rc.aplicar_mapeamento(session, novo, podar=True)
    assert resumo["podadas"] == 0 and resumo["reconstruidas"] > 0
    depois = session.scalar(select(func.count()).select_from(ContaDemonstrativo))
    assert depois == antes + resumo["reconstruidas"]

    # voltar ao mapeamento original poda exatamente o que foi acrescentado
    resumo = rc.aplicar_mapeamento(session, mp.padrao(), podar=True)
    assert (resumo["podadas"], resumo["reconstruidas"]) == (depois - antes, 0)
    contagens = dict(
        session.execute(select(DemonstrativoSiconfi.id, DemonstrativoSiconfi.linhas_gravadas)).all()
    )
    reais = dict(
        session.execute(
            select(ContaDemonstrativo.demonstrativo_id, func.count()).group_by(
                ContaDemonstrativo.demonstrativo_id
            )
        ).all()
    )
    assert all(contagens[d] == reais.get(d, 0) for d in contagens)


def test_relatorio_sem_linhas_no_mapeamento_continua_ligado_ao_bruto(session, coletado):
    # RGF do Legislativo de Adamantina não tem Anexo 5 nem dívida: poucas linhas gravadas,
    # mas o demonstrativo (e a transparência) não somem
    leg = session.scalars(select(DemonstrativoSiconfi).filter_by(poder="L")).all()
    assert leg and all(d.linhas > d.linhas_gravadas for d in leg)
    assert session.scalar(select(func.count()).select_from(DemonstrativoResposta)) > 0
    assert (
        ind.transparencia(session, 3500105, 2025)["blocos"]["rgf_legislativo"]["disponiveis"] == 2
    )


def test_fixture_tem_linhas_fora_do_mapeamento():
    # sanidade: o teste de redução só vale se a resposta real tiver linhas descartáveis
    itens = carregar("adamantina_2025_rgf2_E.json")["items"]
    assert any(not mp.padrao().aceita(i) for i in itens)
    assert json.dumps(itens)  # serializável
