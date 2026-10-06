"""Indicadores fiscais calculados a partir do RREO e do RGF coletados do SICONFI.

Sempre que o relatório já traz o número pronto (percentuais e limites da LRF), ele é
usado tal como declarado pelo ente; só se calcula o que o relatório não traz.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from rastro.models import ContaDemonstrativo, DemonstrativoSiconfi

NOME_PODER = {
    "E": "Executivo",
    "L": "Legislativo",
    "J": "Judiciário",
    "M": "Ministério Público",
    "D": "Defensoria Pública",
}


@dataclass
class Celulas:
    """Valores de um anexo indexados por (cod_conta, coluna)."""

    valores: dict[tuple[str, str], Decimal | None]

    def get(self, cod_conta: str, coluna: str) -> Decimal | None:
        return self.valores.get((cod_conta, coluna))


def _celulas(session: Session, demonstrativo_id: int, anexo: str) -> Celulas:
    linhas = session.execute(
        select(ContaDemonstrativo.cod_conta, ContaDemonstrativo.coluna, ContaDemonstrativo.valor)
        .where(
            ContaDemonstrativo.demonstrativo_id == demonstrativo_id,
            ContaDemonstrativo.anexo == anexo,
        )
        .order_by(ContaDemonstrativo.id)
    ).all()
    valores: dict[tuple[str, str], Decimal | None] = {}
    for cod_conta, coluna, valor in linhas:
        # se a mesma conta e coluna aparecer mais de uma vez, vale a primeira ocorrência
        valores.setdefault((cod_conta, coluna), valor)
    return Celulas(valores)


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
    }
