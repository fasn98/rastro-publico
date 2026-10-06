"""Indicadores fiscais calculados a partir do RREO e do RGF coletados do SICONFI.

Sempre que o relatório já traz o número pronto (percentuais e limites da LRF), ele é
usado tal como declarado pelo ente; só se calcula o que o relatório não traz.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from rastro.models import (
    ContaDemonstrativo,
    DemonstrativoSiconfi,
    EnteSiconfi,
    EntregaSiconfi,
    ExtratoColetado,
)

NOME_PODER = {
    "E": "Executivo",
    "L": "Legislativo",
    "J": "Judiciário",
    "M": "Ministério Público",
    "D": "Defensoria Pública",
}


@dataclass
class Celulas:
    """Linhas de um anexo: (rotulo, cod_conta, conta, coluna, valor)."""

    linhas: list[tuple[str, str, str, str, Decimal | None]]

    def get(self, cod_conta: str, coluna: str) -> Decimal | None:
        """Primeira linha com o código e a coluna (ordem de publicação do relatório)."""
        for _rotulo, cod, _conta, col, valor in self.linhas:
            if cod == cod_conta and col == coluna:
                return valor
        return None

    def get_conta(
        self, conta: str, cod_conta: str, coluna: str | None = None, rotulo: str | None = None
    ) -> Decimal | None:
        """Linha identificada pelo texto da conta.

        Necessário em anexos em que o código não identifica a linha: no RREO Anexo 2 a
        função (Administração, Legislativa...) está no texto; no RGF Anexo 5 o código
        identifica a coluna e o texto ("TOTAL DOS RECURSOS NÃO VINCULADOS (I)") a linha.
        `conta` terminado em "*" casa por prefixo.
        """
        prefixo = conta[:-1] if conta.endswith("*") else None
        for rot, cod, txt, col, valor in self.linhas:
            if cod != cod_conta or (coluna is not None and col != coluna):
                continue
            if rotulo is not None and rot != rotulo:
                continue
            if (prefixo is not None and txt.startswith(prefixo)) or txt == conta:
                return valor
        return None


def _celulas(session: Session, demonstrativo_id: int, anexo: str) -> Celulas:
    linhas = session.execute(
        select(
            ContaDemonstrativo.rotulo,
            ContaDemonstrativo.cod_conta,
            ContaDemonstrativo.conta,
            ContaDemonstrativo.coluna,
            ContaDemonstrativo.valor,
        )
        .where(
            ContaDemonstrativo.demonstrativo_id == demonstrativo_id,
            ContaDemonstrativo.anexo == anexo,
        )
        .order_by(ContaDemonstrativo.id)
    ).all()
    return Celulas([tuple(linha) for linha in linhas])


def periodo_final(d: DemonstrativoSiconfi) -> bool:
    """O demonstrativo é do último período do ano (dado anual)?"""
    return (d.periodicidade, d.periodo) in {("B", 6), ("Q", 3), ("S", 2)}


def _ultimo(session: Session, cod_ibge: int, exercicio: int, prefixo: str):
    """Demonstrativos do último período disponível (RREO ou RGF, completo ou simplificado)."""
    base = select(DemonstrativoSiconfi).where(
        DemonstrativoSiconfi.cod_ibge == cod_ibge,
        DemonstrativoSiconfi.exercicio == exercicio,
        DemonstrativoSiconfi.demonstrativo.startswith(prefixo),
    )
    ultimo = session.scalars(base.order_by(DemonstrativoSiconfi.periodo.desc()).limit(1)).first()
    if not ultimo:
        return []
    return session.scalars(
        base.where(
            DemonstrativoSiconfi.periodo == ultimo.periodo,
            DemonstrativoSiconfi.periodicidade == ultimo.periodicidade,
        ).order_by(DemonstrativoSiconfi.poder, DemonstrativoSiconfi.instituicao)
    ).all()


def _referencia(d: DemonstrativoSiconfi) -> dict:
    return {
        "demonstrativo_id": d.id,
        "demonstrativo": d.demonstrativo,
        "periodicidade": d.periodicidade,
        "periodo": d.periodo,
        "periodo_final": periodo_final(d),
    }


def _situacao(percentual, alerta, prudencial, maximo) -> str | None:
    if percentual is None:
        return None
    if maximo is not None and percentual > maximo:
        return "acima_maximo"
    if prudencial is not None and percentual > prudencial:
        return "acima_prudencial"
    if alerta is not None and percentual > alerta:
        return "acima_alerta"
    return "regular"


def pessoal(session: Session, cod_ibge: int, exercicio: int) -> list[dict]:
    """Despesa total com pessoal sobre a RCL ajustada, por instituição (RGF Anexo 1)."""
    col_pct = "% sobre a RCL Ajustada"
    resultado = []
    for d in _ultimo(session, cod_ibge, exercicio, "RGF"):
        c = _celulas(session, d.id, "RGF-Anexo 01")
        percentual = c.get("DespesaComPessoalTotal", col_pct)
        alerta = c.get("LimiteDeAlertaDespesaComPessoalTotal", col_pct)
        prudencial = c.get("LimitePrudencialDespesaComPessoalTotal", col_pct)
        maximo = c.get("LimiteMaximoDespesaComPessoalTotal", col_pct)
        if percentual is None and c.get("DespesaComPessoalTotal", "Valor") is None:
            continue
        resultado.append(
            {
                **_referencia(d),
                "poder": d.poder,
                "nome_poder": NOME_PODER.get(d.poder or "", d.poder),
                "instituicao": d.instituicao,
                "despesa_total_pessoal": c.get("DespesaComPessoalTotal", "Valor"),
                "rcl_ajustada": c.get("ReceitaCorrenteLiquidaAjustada", "Valor"),
                "percentual": percentual,
                "limite_alerta": alerta,
                "limite_prudencial": prudencial,
                "limite_maximo": maximo,
                "situacao": _situacao(percentual, alerta, prudencial, maximo),
            }
        )
    return resultado


def divida(session: Session, cod_ibge: int, exercicio: int) -> dict | None:
    """Dívida consolidada líquida sobre a RCL ajustada (RGF Anexo 2, Poder Executivo)."""
    executivo = [d for d in _ultimo(session, cod_ibge, exercicio, "RGF") if d.poder == "E"]
    if not executivo:
        return None
    d = executivo[0]
    unidade = "Quadrimestre" if d.periodicidade == "Q" else "Semestre"
    coluna = f"Até o {d.periodo}º {unidade}"
    c = _celulas(session, d.id, "RGF-Anexo 02")
    dcl = c.get("DividaConsolidadaLiquida", coluna)
    rcl = c.get("ReceitaCorrenteLiquidaAjustadaParaCalculoDosLimitesDeEndividamento", coluna)
    if dcl is None or not rcl:
        return None

    def pct(valor):
        return None if valor is None else round(valor / rcl * 100, 2)

    percentual = c.get("PercentualDaDCLSobreARCL", coluna)
    if percentual is None:
        percentual = pct(dcl)
    alerta = pct(c.get("LimiteDeAlerta", coluna))
    maximo = pct(c.get("LimiteDefinidoPorResolucaoDoSenadoFederal", coluna))
    return {
        **_referencia(d),
        "divida_consolidada_liquida": dcl,
        "rcl_ajustada": rcl,
        "percentual": percentual,
        "limite_alerta": alerta,
        "limite_maximo": maximo,
        "situacao": _situacao(percentual, alerta, None, maximo),
    }


def execucao(session: Session, cod_ibge: int, exercicio: int) -> dict | None:
    """Receitas e despesas acumuladas até o último bimestre (RREO Anexo 1)."""
    rreo = _ultimo(session, cod_ibge, exercicio, "RREO")
    if not rreo:
        return None
    d = rreo[0]
    c = _celulas(session, d.id, "RREO-Anexo 01")
    receita = c.get("TotalReceitas", "Até o Bimestre (c)")
    empenhada = c.get("TotalDespesas", "DESPESAS EMPENHADAS ATÉ O BIMESTRE (f)")
    return {
        **_referencia(d),
        "receita_prevista": c.get("TotalReceitas", "PREVISÃO ATUALIZADA (a)"),
        "receita_realizada": receita,
        "despesa_dotacao": c.get("TotalDespesas", "DOTAÇÃO ATUALIZADA (e)"),
        "despesa_empenhada": empenhada,
        "despesa_liquidada": c.get("TotalDespesas", "DESPESAS LIQUIDADAS ATÉ O BIMESTRE (h)"),
        "despesa_paga": c.get("TotalDespesas", "DESPESAS PAGAS ATÉ O BIMESTRE (j)"),
        # receita realizada menos despesa empenhada; negativo = déficit orçamentário
        "resultado": None if receita is None or empenhada is None else receita - empenhada,
        # saldo de exercícios anteriores usado para cobrir despesas deste exercício
        "superavit_financeiro_utilizado": c.get("SuperavitFinanceiro", "Até o Bimestre (c)"),
    }


def _razao(a: Decimal | None, b: Decimal | None, escala: int = 1) -> Decimal | None:
    if a is None or not b:
        return None
    return round(a / b * escala, 4)


def autonomia(session: Session, cod_ibge: int, exercicio: int) -> dict | None:
    """(Receita tributária própria + cotas-parte de ICMS, IPVA e ITR) ÷ (funções Administração
    + Legislativa). Quanto a receita ligada à economia local cobre a estrutura administrativa.
    """
    rreo = _ultimo(session, cod_ibge, exercicio, "RREO")
    if not rreo:
        return None
    d = rreo[0]
    a1 = _celulas(session, d.id, "RREO-Anexo 01")
    a2 = _celulas(session, d.id, "RREO-Anexo 02")
    a3 = _celulas(session, d.id, "RREO-Anexo 03")
    col3 = "TOTAL (ÚLTIMOS 12 MESES)"
    col2 = "DESPESAS EMPENHADAS ATÉ O BIMESTRE (b)"
    rotulo2 = "Total das Despesas Exceto Intra-Orçamentárias"
    tributaria = a1.get("ReceitaTributaria", "Até o Bimestre (c)")
    cotas = {
        "cota_icms": a3.get("RREO3CotaParteDoICMS", col3),
        "cota_ipva": a3.get("RREO3CotaParteDoIPVA", col3),
        "cota_itr": a3.get("RREO3CotaParteDoITR", col3),
    }
    administracao = a2.get_conta("Administração", "RREO2TotalDespesas", col2, rotulo2)
    legislativa = a2.get_conta("Legislativa", "RREO2TotalDespesas", col2, rotulo2)
    # sem receita tributária ou sem a função Administração não há como calcular
    if tributaria is None or administracao is None:
        receita = custo = None
    else:
        # a API omite linhas com valor zero: cota-parte ou função ausente conta como 0
        receita = tributaria + sum((v or 0) for v in cotas.values())
        custo = administracao + (legislativa or 0)
    return {
        **_referencia(d),
        "receita_tributaria": tributaria,
        **cotas,
        "despesa_administracao": administracao,
        "despesa_legislativa": legislativa,
        "receita_local": receita,
        "custo_estrutura": custo,
        "razao": _razao(receita, custo),
    }


def liquidez(session: Session, cod_ibge: int, exercicio: int) -> dict | None:
    """Caixa líquido após restos a pagar dos recursos não vinculados ÷ RCL (RGF Anexo 5,
    Executivo). Só existe no último período do ano (3º quadrimestre ou 2º semestre).
    """
    executivo = [d for d in _ultimo(session, cod_ibge, exercicio, "RGF") if d.poder == "E"]
    if not executivo or not periodo_final(executivo[0]):
        return None
    d = executivo[0]
    a5 = _celulas(session, d.id, "RGF-Anexo 05")
    cod = "DisponibilidadeDeCaixaLiquidaAposRP"
    nao_vinculados = a5.get_conta("TOTAL DOS RECURSOS NÃO VINCULADOS*", cod)
    vinculados = None
    for _rot, c, txt, _col, valor in a5.linhas:
        # (II) vinculados exceto RPPS; o RPPS (III) fica de fora
        if c == cod and txt.startswith("TOTAL DOS RECURSOS VINCULADOS") and "AO RPPS (" not in txt:
            vinculados = valor
            break
    unidade = "Quadrimestre" if d.periodicidade == "Q" else "Semestre"
    rcl = _celulas(session, d.id, "RGF-Anexo 02").get(
        "RGF2ReceitaCorrenteLiquida", f"Até o {d.periodo}º {unidade}"
    )
    soma = None if nao_vinculados is None else nao_vinculados + (vinculados or 0)
    return {
        **_referencia(d),
        "caixa_liquido_nao_vinculado": nao_vinculados,
        "caixa_liquido_vinculado": vinculados,
        "rcl": rcl,
        "percentual": _razao(nao_vinculados, rcl, 100),
        # contexto, fora da nota: não vinculados + vinculados (exceto RPPS)
        "percentual_com_vinculados": _razao(soma, rcl, 100),
    }


def investimento(session: Session, cod_ibge: int, exercicio: int) -> dict | None:
    """Investimentos liquidados (exceto intra) ÷ receita total realizada (RREO Anexo 1)."""
    rreo = _ultimo(session, cod_ibge, exercicio, "RREO")
    if not rreo:
        return None
    d = rreo[0]
    a1 = _celulas(session, d.id, "RREO-Anexo 01")
    liquidado = a1.get("Investimentos", "DESPESAS LIQUIDADAS ATÉ O BIMESTRE (h)")
    receita = a1.get("TotalReceitas", "Até o Bimestre (c)")
    return {
        **_referencia(d),
        "liquidado": liquidado,
        "empenhado": a1.get("Investimentos", "DESPESAS EMPENHADAS ATÉ O BIMESTRE (f)"),
        "restos_a_pagar_nao_processados": a1.get(
            "Investimentos", "INSCRITAS EM RESTOS A PAGAR NÃO PROCESSADOS (k)"
        ),
        "receita_realizada": receita,
        "percentual": _razao(liquidado, receita, 100),
    }


# Municípios com até 50 mil habitantes podem optar pelo RGF semestral (art. 63 da LRF).
LIMITE_POPULACAO_SEMESTRAL = 50_000


def transparencia(session: Session, cod_ibge: int, exercicio: int) -> dict | None:
    """Relatórios obrigatórios disponíveis na API ÷ esperados, em 4 blocos de peso igual:
    RREO (6 bimestres), RGF do Executivo, RGF do Legislativo e DCA. PROVISÓRIO.

    "Disponível" = o ente entregou e a API devolveu as linhas. Retificações não penalizam
    e a pontualidade não é medida (a data do extrato muda quando o ente retifica).
    Devolve None se o extrato do ano ainda não foi coletado.
    """
    if session.get(ExtratoColetado, (cod_ibge, exercicio)) is None:
        return None
    entregas = session.scalars(
        select(EntregaSiconfi).where(
            EntregaSiconfi.cod_ibge == cod_ibge, EntregaSiconfi.exercicio == exercicio
        )
    ).all()
    demonstrativos = session.scalars(
        select(DemonstrativoSiconfi).where(
            DemonstrativoSiconfi.cod_ibge == cod_ibge, DemonstrativoSiconfi.exercicio == exercicio
        )
    ).all()

    # periodicidade do RGF: a que o ente usou no extrato; sem RGF nenhum, a mínima exigida
    usadas = [
        e.periodicidade for e in entregas if e.entregavel.startswith("Relatório de Gestão Fiscal")
    ]
    if usadas:
        periodicidade = max(set(usadas), key=usadas.count)
    else:
        ente = session.get(EnteSiconfi, cod_ibge)
        pequeno = ente and ente.populacao and ente.populacao <= LIMITE_POPULACAO_SEMESTRAL
        periodicidade = "S" if pequeno else "Q"
    n_rgf = 2 if periodicidade == "S" else 3

    rreo = {d.periodo for d in demonstrativos if d.demonstrativo.startswith("RREO")}

    def rgf(poder: str) -> set[int]:
        return {
            d.periodo
            for d in demonstrativos
            if d.demonstrativo.startswith("RGF")
            and d.poder == poder
            and d.periodicidade == periodicidade
        }

    dca = any(e.entregavel == "Balanço Anual (DCA)" for e in entregas)
    blocos = {
        "rreo": {"disponiveis": len(rreo & set(range(1, 7))), "esperados": 6},
        "rgf_executivo": {
            "disponiveis": len(rgf("E") & set(range(1, n_rgf + 1))),
            "esperados": n_rgf,
        },
        "rgf_legislativo": {
            "disponiveis": len(rgf("L") & set(range(1, n_rgf + 1))),
            "esperados": n_rgf,
        },
        "dca": {"disponiveis": int(dca), "esperados": 1},
    }
    indice = sum(Decimal(b["disponiveis"]) / b["esperados"] for b in blocos.values()) / len(blocos)
    return {
        "exercicio": exercicio,
        "periodicidade_rgf": periodicidade,
        "blocos": blocos,
        "indice": round(indice, 4),
        "provisorio": True,
    }


def exercicios_disponiveis(session: Session, cod_ibge: int) -> list[int]:
    return list(
        session.scalars(
            select(DemonstrativoSiconfi.exercicio)
            .where(DemonstrativoSiconfi.cod_ibge == cod_ibge)
            .distinct()
            .order_by(DemonstrativoSiconfi.exercicio.desc())
        )
    )


def indicadores(session: Session, cod_ibge: int, exercicio: int) -> dict:
    return {
        "cod_ibge": cod_ibge,
        "exercicio": exercicio,
        "pessoal": pessoal(session, cod_ibge, exercicio),
        "divida": divida(session, cod_ibge, exercicio),
        "execucao": execucao(session, cod_ibge, exercicio),
        "autonomia": autonomia(session, cod_ibge, exercicio),
        "liquidez": liquidez(session, cod_ibge, exercicio),
        "investimento": investimento(session, cod_ibge, exercicio),
        "transparencia": transparencia(session, cod_ibge, exercicio),
    }


def serie(session: Session, cod_ibge: int) -> list[dict]:
    """Indicadores de cada exercício coletado, do mais antigo para o mais recente."""
    return [
        indicadores(session, cod_ibge, a) for a in sorted(exercicios_disponiveis(session, cod_ibge))
    ]
