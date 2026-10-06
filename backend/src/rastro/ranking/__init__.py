"""Ranking Fiscal: normaliza os indicadores de 0 a 1, faz a média dos últimos exercícios e
combina com pesos, segundo as regras de um arquivo de metodologia (TOML).

Regras gerais (valem para qualquer versão da metodologia):

- Só entram dados anuais: RREO do 6º bimestre e RGF do último período do ano.
- Cada indicador é normalizado ano a ano e depois tem a média dos anos com dado.
- Indicador sem nenhum ano com dado = "não reportado": fica fora da média ponderada
  (os pesos são redistribuídos) e entra na contagem de indicadores faltantes.
  Exceção: a transparência, em que ausência de relatório vale 0.
- Abaixo de `minimo_indicadores_fiscais`, o município fica sem nota.
"""

import hashlib
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from rastro import indicadores as ind
from rastro.models import EnteSiconfi, NotaRanking

ARQUIVO_PADRAO = Path(__file__).with_name("metodologia_v1.toml")
FISCAIS = ("autonomia", "pessoal", "liquidez", "investimento")


@dataclass
class Metodologia:
    regras: dict
    hash: str

    @property
    def versao(self) -> str:
        return self.regras["versao"]

    @property
    def exercicios(self) -> list[int]:
        fim = self.regras["ultimo_exercicio"]
        return list(range(fim - self.regras["janela_exercicios"] + 1, fim + 1))


def carregar_metodologia(caminho: Path = ARQUIVO_PADRAO) -> Metodologia:
    conteudo = caminho.read_bytes()
    return Metodologia(tomllib.loads(conteudo.decode()), hashlib.sha256(conteudo).hexdigest()[:12])


def faixa_populacional(populacao: int | None, faixas: list[dict]) -> str | None:
    if populacao is None:
        return None
    for f in faixas:
        if "ate" not in f or populacao <= f["ate"]:
            return f["nome"]
    return None


def normalizar(valor: float, pior: float, melhor: float) -> float:
    """Linear entre `pior` (0) e `melhor` (1), limitado a [0, 1]."""
    if melhor == pior:
        return 1.0 if valor >= melhor else 0.0
    return min(1.0, max(0.0, (valor - pior) / (melhor - pior)))


def valores_do_ano(session: Session, cod_ibge: int, exercicio: int) -> dict[str, dict | None]:
    """Valor bruto de cada indicador no ano, só com relatórios do último período."""

    def final(d):
        return d if d and d.get("periodo_final") else None

    executivo = final(
        next((p for p in ind.pessoal(session, cod_ibge, exercicio) if p["poder"] == "E"), None)
    )
    autonomia = final(ind.autonomia(session, cod_ibge, exercicio))
    investimento = final(ind.investimento(session, cod_ibge, exercicio))
    liquidez = ind.liquidez(session, cod_ibge, exercicio)  # já só existe no período final
    transparencia = ind.transparencia(session, cod_ibge, exercicio)

    def item(valor, **extra):
        return None if valor is None else {"valor": float(valor), **extra}

    return {
        "autonomia": item(autonomia and autonomia["razao"]),
        "pessoal": item(
            executivo and executivo["percentual"],
            limite_maximo=float(executivo["limite_maximo"])
            if executivo and executivo["limite_maximo"] is not None
            else None,
        ),
        "liquidez": item(liquidez and liquidez["percentual"]),
        "investimento": item(investimento and investimento["percentual"]),
        "transparencia": item(transparencia and transparencia["indice"]),
    }


def _nota_ano(dado: dict | None, regra: dict) -> float | None:
    if dado is None:
        return None
    pior, melhor = regra["pior"], regra["melhor"]
    if regra.get("relativo_ao_limite_maximo"):
        limite = dado.get("limite_maximo")
        if not limite:
            return None
        pior, melhor = pior * limite, melhor * limite
    return normalizar(dado["valor"], pior, melhor)


def avaliar(session: Session, ente: EnteSiconfi, met: Metodologia) -> dict:
    """Nota de um município, com o detalhe de cada indicador e ano."""
    regras = met.regras["indicadores"]
    por_ano = {a: valores_do_ano(session, ente.cod_ibge, a) for a in met.exercicios}
    componentes = {}
    for nome, regra in regras.items():
        anos = {}
        for a in met.exercicios:
            dado = por_ano[a][nome]
            anos[str(a)] = {
                "valor": dado["valor"] if dado else None,
                "nota": _nota_ano(dado, regra),
            }
        notas = [x["nota"] for x in anos.values() if x["nota"] is not None]
        componentes[nome] = {
            "nota": round(sum(notas) / len(notas), 4) if notas else None,
            "anos_com_dado": len(notas),
            "peso": regra["peso"],
            "anos": anos,
        }

    faltantes = [n for n, c in componentes.items() if c["nota"] is None]
    fiscais_presentes = sum(1 for n in FISCAIS if componentes[n]["nota"] is not None)
    presentes = [c for c in componentes.values() if c["nota"] is not None]
    peso_total = sum(c["peso"] for c in presentes)
    if fiscais_presentes < met.regras["minimo_indicadores_fiscais"] or not peso_total:
        nota = None
    else:
        nota = round(sum(c["nota"] * c["peso"] for c in presentes) / peso_total, 4)
    return {
        "cod_ibge": ente.cod_ibge,
        "nome": ente.nome,
        "uf": ente.uf,
        "populacao": ente.populacao,
        "faixa": faixa_populacional(ente.populacao, met.regras["faixas"]),
        "nota": nota,
        "indicadores_faltantes": len(faltantes),
        "faltantes": faltantes,
        "componentes": componentes,
    }


def _posicoes(itens: list[dict], chave: str, grupo: str | None = None) -> None:
    """Posição por competição (empates dividem a posição: 1, 2, 2, 4)."""
    grupos: dict[str | None, list[dict]] = {}
    for i in itens:
        if i["nota"] is not None:
            grupos.setdefault(i[grupo] if grupo else None, []).append(i)
    for membros in grupos.values():
        membros.sort(key=lambda i: -i["nota"])
        anterior, posicao = None, 0
        for n, i in enumerate(membros, start=1):
            if i["nota"] != anterior:
                posicao, anterior = n, i["nota"]
            i[chave] = posicao


def calcular(session: Session, uf: str, met: Metodologia | None = None) -> list[dict]:
    """Calcula e grava o ranking de todos os municípios da UF (substitui o da mesma versão)."""
    met = met or carregar_metodologia()
    entes = session.scalars(
        select(EnteSiconfi)
        .where(EnteSiconfi.uf == uf.upper(), EnteSiconfi.esfera == "M")
        .order_by(EnteSiconfi.cod_ibge)
    ).all()
    itens = [avaliar(session, e, met) for e in entes]
    _posicoes(itens, "posicao_geral")
    _posicoes(itens, "posicao_faixa", "faixa")

    session.execute(
        delete(NotaRanking).where(NotaRanking.versao == met.versao, NotaRanking.uf == uf.upper())
    )
    agora = datetime.now(UTC)
    session.add_all(
        NotaRanking(
            versao=met.versao,
            hash_metodologia=met.hash,
            calculado_em=agora,
            exercicios=",".join(map(str, met.exercicios)),
            cod_ibge=i["cod_ibge"],
            uf=i["uf"],
            populacao=i["populacao"],
            faixa=i["faixa"],
            nota=Decimal(str(i["nota"])) if i["nota"] is not None else None,
            indicadores_faltantes=i["indicadores_faltantes"],
            posicao_geral=i.get("posicao_geral"),
            posicao_faixa=i.get("posicao_faixa"),
            componentes=i["componentes"],
        )
        for i in itens
    )
    session.commit()
    return itens
