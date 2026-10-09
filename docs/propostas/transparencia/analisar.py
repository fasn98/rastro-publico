"""Pontualidade das entregas ao SICONFI, municípios de SP, 2023-2025.

Fonte: extrato_entregas da API de dados abertos do SICONFI (raw/{cod}_{ano}.json).
Prazos: Portaria STN 642/2019 (atualizada), arts. 4º §3º (DCA, 30/4), 6º (RREO e RGF, 30 dias
após o fim do período; semestral: 30 dias após o semestre) e 8º §2º (MSC: último dia do mês
seguinte). data_status em UTC, convertida para o horário de Brasília (UTC-3).
"""

import calendar
import glob
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

RAW = os.path.join(os.path.dirname(__file__), "raw")
RANKING = sys.argv[1]
ANOS = (2023, 2024, 2025)


def fim_mes(a, m):
    if m > 12:
        a, m = a + 1, m - 12
    return date(a, m, calendar.monthrange(a, m)[1])


def dia(s):
    return (datetime.fromisoformat(s.replace("Z", "+00:00")) - timedelta(hours=3)).date()


def tipo(x):
    e = x["entregavel"]
    i = (x.get("instituicao") or "").lower()
    if e.startswith("Relatório Resumido"):
        return "rreo" if "prefeitura" in i else None
    if e.startswith("Relatório de Gestão Fiscal"):
        if "prefeitura" in i:
            return "rgf_executivo"
        if "câmara" in i or "camara" in i:
            return "rgf_legislativo"
        return None
    if e == "Balanço Anual (DCA)":
        return "dca" if "prefeitura" in i else None
    if e == "MSC Agregada":
        return "msc"
    return None


def prazo(t, per, periodicidade, ano):
    if t == "rreo":
        return fim_mes(ano, 2 * per) + timedelta(days=30)
    if t.startswith("rgf"):
        meses = 6 if periodicidade == "S" else 4
        return fim_mes(ano, meses * per) + timedelta(days=30)
    if t == "dca":
        return date(ano + 1, 4, 30)
    if t == "msc":
        return fim_mes(ano, per + 1)


def esperados(t, periodicidade):
    return {"rreo": 6, "dca": 1, "msc": 12}.get(t) or (2 if periodicidade == "S" else 3)


# situação de cada item esperado: "prazo", "atraso", "retificado" (data original perdida), "falta"
itens = {}  # (cod, ano) -> {bloco: [situações]}
atrasos = defaultdict(list)  # bloco -> dias de atraso (só HO/MSC)
faltam = []
for cod in open(os.path.join(os.path.dirname(__file__), "codigos.txt")).read().split():
    for ano in ANOS:
        f = os.path.join(RAW, f"{cod}_{ano}.json")
        if not os.path.exists(f):
            faltam.append((cod, ano))
            continue
        regs = [x for x in json.load(open(f))["items"] if x.get("exercicio", ano) == ano]
        por = defaultdict(list)
        for x in regs:
            t = tipo(x)
            if t:
                por[(t, x["periodo"])].append(x)
        blocos = {}
        for t in ("rreo", "rgf_executivo", "rgf_legislativo", "dca", "msc"):
            pers = [x["periodicidade"] for (tt, _), xs in por.items() if tt == t for x in xs]
            per_rgf = Counter(pers).most_common(1)[0][0] if pers else "Q"
            n = esperados(t, per_rgf)
            sit = []
            for p in range(1, n + 1):
                xs = por.get((t, p), [])
                if not xs:
                    sit.append("falta")
                    continue
                # mais de um registro (ex.: MSC listada por instituição): vale o primeiro envio
                x = min(xs, key=lambda x: x["data_status"])
                if x.get("status_relatorio") == "RE":
                    sit.append("retificado")
                    continue
                d = (dia(x["data_status"]) - prazo(t, p, per_rgf, ano)).days
                atrasos[t].append(d)
                sit.append("prazo" if d <= 0 else "atraso30" if d <= 30 else "atraso")
            blocos[t] = sit
        itens[(cod, ano)] = blocos

print(f"município-anos lidos: {len(itens)}; sem arquivo: {len(faltam)}")
print()
print("Situação dos itens esperados, 2023-2025")
print("| bloco | esperados | no prazo | com atraso | retificado (data original perdida) | não entregue |")
print("|---|---|---|---|---|---|")
for t in ("rreo", "rgf_executivo", "rgf_legislativo", "dca", "msc"):
    c = Counter(("atraso" if s == "atraso30" else s) for b in itens.values() for s in b[t])
    tot = sum(c.values())
    pct = lambda k: f"{c[k]:,} ({100 * c[k] / tot:.1f}%)".replace(",", ".")
    print(f"| {t} | {tot:,} | {pct('prazo')} | {pct('atraso')} | {pct('retificado')} | {pct('falta')} |".replace(",", "."))
print()
print("Dias de atraso entre os entregues com atraso (mediana / p90 / máximo)")
for t, ds in atrasos.items():
    at = sorted(d for d in ds if d > 0)
    if at:
        print(f"- {t}: {len(at)} itens; mediana {statistics.median(at)}; "
              f"p90 {at[int(0.9 * (len(at) - 1))]}; máximo {at[-1]}")


def indice(blocos, regra, com_msc):
    nomes = ["rreo", "rgf_executivo", "rgf_legislativo", "dca"] + (["msc"] if com_msc else [])
    vals = []
    for t in nomes:
        sit = blocos[t]
        pts = [regra[s] for s in sit if regra[s] is not None]
        den = len([s for s in sit if regra[s] is not None])
        vals.append(sum(pts) / den if den else 1.0)
    return sum(vals) / len(vals)


REGRAS = {
    # entregue = 1, como hoje (só a presença no extrato; hoje usamos as linhas na API)
    "E0: entregue (base: presença no extrato)": (
        {"prazo": 1, "atraso30": 1, "atraso": 1, "retificado": 1, "falta": 0}, False),
    "E1: E0 + MSC mensal como 5º bloco (presença)": (
        {"prazo": 1, "atraso30": 1, "atraso": 1, "retificado": 1, "falta": 0}, True),
    "P1: no prazo = 1, atraso = 0,5, falta = 0; retificado = 1": (
        {"prazo": 1, "atraso30": 0.5, "atraso": 0.5, "retificado": 1, "falta": 0}, False),
    "P2: P1 + MSC no prazo como 5º bloco": (
        {"prazo": 1, "atraso30": 0.5, "atraso": 0.5, "retificado": 1, "falta": 0}, True),
    "P3: P2, mas retificado fora da conta": (
        {"prazo": 1, "atraso30": 0.5, "atraso": 0.5, "retificado": None, "falta": 0}, True),
    "P4: P2 com atraso = 0 (só conta o que chegou no prazo)": (
        {"prazo": 1, "atraso30": 0, "atraso": 0, "retificado": 1, "falta": 0}, True),
    "P5: P2 com tolerância: até 30 dias de atraso = 1, mais de 30 = 0,5": (
        {"prazo": 1, "atraso30": 1, "atraso": 0.5, "retificado": 1, "falta": 0}, True),
}

rk = json.load(open(RANKING))
fiscal = {}
publicada = {}
for i in rk["itens"]:
    ns = i["notas"]
    f = [ns[k] for k in ("autonomia", "investimento", "liquidez", "pessoal") if ns.get(k) is not None]
    if i["nota"] is not None:
        fiscal[str(i["cod_ibge"])] = statistics.mean(f)
        publicada[str(i["cod_ibge"])] = float(i["nota"])


def faixas(notas):
    c = [0] * 5
    for n in notas:
        c[min(int(n * 10 // 2), 4)] += 1
    return " / ".join(map(str, c))


def posicoes(d):
    ordem = sorted(d, key=lambda k: -d[k])
    return {k: r for r, k in enumerate(ordem, 1)}


def spearman(a, b):
    ra, rb = posicoes(a), posicoes(b)
    n = len(ra)
    return 1 - 6 * sum((ra[k] - rb[k]) ** 2 for k in ra) / (n * (n * n - 1))


print()
print("Índice por município (média 2023-2025) e efeito na nota (multiplicador, como na v1.1)")
print("| regra | índice = 1 | 1º quartil | mediana | mínimo | nota 0-2/2-4/4-6/6-8/8-10 | mediana da nota | correlação de posições com a publicada | maior queda de posição |")
print("|---|---|---|---|---|---|---|---|---|")
print(f"| publicada (v1.1) | | | | | {faixas(publicada.values())} | "
      f"{statistics.median(publicada.values()) * 10:.2f} | 1 | |")
for nome, (regra, com_msc) in REGRAS.items():
    idx = {}
    for cod in fiscal:
        vs = [indice(itens[(cod, a)], regra, com_msc) for a in ANOS if (cod, a) in itens]
        idx[cod] = statistics.mean(vs)
    nota = {c: fiscal[c] * idx[c] for c in fiscal}
    v = sorted(idx.values())
    q1 = v[len(v) // 4]
    rp, rn = posicoes(publicada), posicoes(nota)
    queda = max(rn[c] - rp[c] for c in rp)
    print(f"| {nome} | {sum(1 for x in v if x >= 0.99995)} ({100 * sum(1 for x in v if x >= 0.99995) / len(v):.0f}%) | "
          f"{q1:.3f} | {statistics.median(v):.3f} | {v[0]:.3f} | {faixas(nota.values())} | "
          f"{statistics.median(nota.values()) * 10:.2f} | {spearman(publicada, nota):.3f} | {queda} |")
