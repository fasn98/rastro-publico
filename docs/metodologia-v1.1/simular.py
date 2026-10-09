"""Simulação da metodologia v1.1 do Ranking Fiscal, com os dados publicados em 08/10/2026
(site-20261008-223829) e correções verificadas na API do SICONFI."""
import collections
import glob
import json
import statistics as st
import sys
from pathlib import Path

# uso: python simular.py <pasta dados/ da publicação site-20261008-223829>
#   git archive site-20261008-223829 dados/municipios | tar -x -C /tmp/v11
#   python docs/metodologia-v1.1/simular.py /tmp/v11/dados
DADOS = sys.argv[1]
AQUI = str(Path(__file__).parent)

ANOS = ("2023", "2024", "2025")
FISCAIS = ("autonomia", "pessoal", "liquidez", "investimento")
M = [json.load(open(f)) for f in sorted(glob.glob(DADOS + "/municipios/*.json"))]
LIQ = json.load(open(AQUI + "/liq_derivada.json"))
CORR = json.load(open(AQUI + "/correcoes.json"))
POP = json.load(open(AQUI + "/populacao.json"))
out = []


def p(*a):
    out.append(" ".join(str(x) for x in a))


def norm(v, pior, melhor):
    return min(1.0, max(0.0, (v - pior) / (melhor - pior)))


def br(x, d=1):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def calcula(m, *, leitura=False, pessoal_max=None, teto_aut=10.0, transp="peso1"):
    cod = str(m["detalhe"]["cod_ibge"])
    comp = m["nota"]["componentes"]
    notas = {}
    for k in FISCAIS + ("transparencia",):
        anos = []
        for y in ANOS:
            a = comp[k]["anos"][y]
            v, n = a["valor"], a["nota"]
            chave = f"{cod}_{y}"
            if leitura and chave in CORR and k in CORR[chave]:
                v, n = CORR[chave][k], "recalc"
            if leitura and k == "liquidez" and v is None and chave in LIQ:
                v, n = LIQ[chave]["percentual"], "recalc"
            if v is None:
                continue
            if k == "autonomia":
                n = norm(v, 1.0, teto_aut)
            elif k == "liquidez" and n == "recalc":
                n = norm(v, 0.0, 20.0)
            elif k == "investimento" and n == "recalc":
                n = norm(v, 0.0, 10.0)
            elif k == "pessoal" and pessoal_max is not None and v > pessoal_max:
                continue
            anos.append(n)
        notas[k] = round(sum(anos) / len(anos), 4) if anos else None
    fisc = [notas[k] for k in FISCAIS if notas[k] is not None]
    if len(fisc) < 3:
        return None, notas
    t = notas["transparencia"]
    if transp == "peso1":
        pres = fisc + ([t] if t is not None else [])
        return round(sum(pres) / len(pres), 4), notas
    if transp == "peso05":
        w = 0.5 if t is not None else 0
        return round((sum(fisc) + w * (t or 0)) / (len(fisc) + w), 4), notas
    if transp == "fora":
        return round(sum(fisc) / len(fisc), 4), notas
    if transp == "multiplica":
        return round(sum(fisc) / len(fisc) * (t if t is not None else 1), 4), notas
    raise ValueError(transp)


def ranking(d):
    itens = sorted(((v, k) for k, v in d.items() if v is not None), reverse=True)
    pos, ant, r = 0, None, {}
    for i, (v, k) in enumerate(itens, 1):
        if v != ant:
            pos, ant = i, v
        r[k] = pos
    return r


def spearman(a, b):
    ks = [k for k in a if a[k] is not None and b[k] is not None]
    ra, rb = ranking({k: a[k] for k in ks}), ranking({k: b[k] for k in ks})
    n = len(ks)
    return 1 - 6 * sum((ra[k] - rb[k]) ** 2 for k in ks) / (n * (n * n - 1))


def resumo(d):
    ns = [v * 10 for v in d.values() if v is not None]
    c = collections.Counter(min(int(v // 2), 4) for v in ns)
    return len(ns), [c[i] for i in range(5)], min(ns), st.median(ns), max(ns), st.pstdev(ns)


NOME = {str(m["detalhe"]["cod_ibge"]): m["detalhe"]["nome"] for m in M}
VAL = lambda **kw: {str(m["detalhe"]["cod_ibge"]): calcula(m, **kw)[0] for m in M}  # noqa: E731

# ---------------------------------------------------------------- 1. distribuições
p("## 1. Distribuição real de cada indicador (2023–2025, município-ano, como publicado)\n")
p("| Indicador | n | mínimo | 1º quartil | mediana | 3º quartil | máximo | âncoras v1.0 | % no teto | % no piso |")
p("|---|---|---|---|---|---|---|---|---|---|")
anc = {"autonomia": ("1 → 10", 1.0, 10.0), "pessoal": ("100% → 70% do limite (54% → 37,8%)", 54.0, 37.8),
       "liquidez": ("0% → 20%", 0.0, 20.0), "investimento": ("0% → 10%", 0.0, 10.0)}
for k in FISCAIS:
    v = sorted(a["valor"] for m in M for a in m["nota"]["componentes"][k]["anos"].values() if a["valor"] is not None)
    q = st.quantiles(v, n=4)
    rot, pior, melhor = anc[k]
    teto = sum(1 for x in v if (x >= melhor if melhor > pior else x <= melhor)) / len(v) * 100
    piso = sum(1 for x in v if (x <= pior if melhor > pior else x >= pior)) / len(v) * 100
    p(f"| {k} | {len(v)} | {br(v[0],2)} | {br(q[0],2)} | {br(q[1],2)} | {br(q[2],2)} | {br(v[-1],2)} | {rot} | {br(teto)}% | {br(piso)}% |")
tv = [a["valor"] for m in M for a in m["nota"]["componentes"]["transparencia"]["anos"].values() if a["valor"] is not None]
p(f"| transparência | {len(tv)} | {br(min(tv),2)} | {br(st.quantiles(tv,n=4)[0],2)} | {br(st.median(tv),2)} | {br(st.quantiles(tv,n=4)[2],2)} | {br(max(tv),2)} | 0 → 1 | {br(sum(x>=1 for x in tv)/len(tv)*100)}% | {br(sum(x<=0 for x in tv)/len(tv)*100)}% |")
au = sorted(a["valor"] for m in M for a in m["nota"]["componentes"]["autonomia"]["anos"].values() if a["valor"] is not None)
dec = st.quantiles(au, n=20)
p(f"\nAutonomia: percentil 90 = {br(dec[17],2)}, percentil 95 = {br(dec[18],2)}.")
pe = [a["valor"] for m in M for a in m["nota"]["componentes"]["pessoal"]["anos"].values() if a["valor"] is not None]
p(f"Pessoal acima de 100% da RCL: {sum(x>100 for x in pe)} município-anos; acima de 70%: {sum(x>70 for x in pe)}.")

# ---------------------------------------------------------------- 2. transparência
base = VAL()
p("\n## 2. Transparência: opções e efeito\n")
p("Todas com as correções de leitura e o teto da autonomia 7 (ver item 4).\n")
p("| Opção | com nota | 0–2 / 2–4 / 4–6 / 6–8 / 8–10 | mín | mediana | máx | desvio | correlação de posições com a v1.0 |")
p("|---|---|---|---|---|---|---|---|")
comum = dict(leitura=True, teto_aut=7.0)
opc = {"peso1": "T0: peso 1 (como na v1.0)", "peso05": "T1: peso 0,5", "fora": "T2: fora da nota (só informativa)",
       "multiplica": "T3: multiplicador (nota fiscal × índice)"}
VARS = {}
for t, rot in opc.items():
    VARS[t] = VAL(**comum, transp=t)
    n, f, mn, md, mx, dp = resumo(VARS[t])
    p(f"| {rot} | {n} | {' / '.join(map(str,f))} | {br(mn)} | {br(md)} | {br(mx)} | {br(dp,2)} | {br(spearman(base,VARS[t]),3)} |")
MSC = json.load(open(AQUI + "/msc.json"))  # extrato de entregas do SICONFI, por município-ano
completos = sum(1 for v in MSC.values() if v["meses"] == 12 and v["encerramento"])
p(f"| T4: incluir a MSC no índice | igual a T0: {completos} de {len(MSC)} município-anos (2023–2025) com as 12 MSC mensais e a de encerramento entregues | | | | | | |")
abaixo = [(NOME[str(m['detalhe']['cod_ibge'])], y, a["valor"]) for m in M for y, a in m["nota"]["componentes"]["transparencia"]["anos"].items() if a["valor"] is not None and a["valor"] < 1]
p(f"\nMunicípio-anos com transparência abaixo de 1: {len(abaixo)}: " + "; ".join(f"{n} {y} ({br(v,2)})" for n, y, v in abaixo))

# ---------------------------------------------------------------- 3. população
p("\n## 3. Faixas populacionais e per capita com o IBGE\n")
fx = [(10_000, "até 10 mil"), (50_000, "10 a 50 mil"), (100_000, "50 a 100 mil"), (500_000, "100 a 500 mil"), (None, "acima de 500 mil")]
faixa = lambda x: next(n for a, n in fx if a is None or x <= a)  # noqa: E731
muda = [(m["detalhe"]["nome"], m["detalhe"]["ente_siconfi"]["populacao"], POP[str(m["detalhe"]["cod_ibge"])]["est2025"])
        for m in M if faixa(m["detalhe"]["ente_siconfi"]["populacao"]) != faixa(POP[str(m["detalhe"]["cod_ibge"])]["est2025"])]
p(f"Municípios que mudam de faixa trocando a população do SICONFI pela estimativa IBGE 2025: {len(muda)}" + (": " + "; ".join(f"{a} ({br(b,0)} → {br(c,0)})" for a, b, c in muda) if muda else "."))
cont = collections.Counter(faixa(POP[str(m["detalhe"]["cod_ibge"])]["est2025"]) for m in M)
p("Municípios por faixa (IBGE 2025): " + "; ".join(f"{n}: {cont[n]}" for _, n in fx))
popano = {"2023": "censo2022", "2024": "est2024", "2025": "est2025"}
pc = {"receita local per capita (R$)": [], "investimento liquidado per capita (R$)": []}
for m in M:
    cod = str(m["detalhe"]["cod_ibge"])
    for s in m["serie"]:
        y = str(s["exercicio"])
        if y not in ANOS:
            continue
        pp = POP[cod][popano[y]]
        a, i = s.get("autonomia") or {}, s.get("investimento") or {}
        if f"{cod}_{y}" in CORR:
            b = CORR[f"{cod}_{y}"]["_bruto"]
            a = {"receita_local": b["trib"] + b["cotas"]}
            i = {"liquidado": b["inv"]}
        if a.get("receita_local"):
            pc["receita local per capita (R$)"].append(float(a["receita_local"]) / pp)
        if i.get("liquidado"):
            pc["investimento liquidado per capita (R$)"].append(float(i["liquidado"]) / pp)
p("\n| Per capita (2023–2025, município-ano) | n | mínimo | 1º quartil | mediana | 3º quartil | máximo |\n|---|---|---|---|---|---|---|")
for k, v in pc.items():
    v = sorted(v)
    q = st.quantiles(v, n=4)
    p(f"| {k} | {len(v)} | {br(v[0],0)} | {br(q[0],0)} | {br(q[1],0)} | {br(q[2],0)} | {br(v[-1],0)} |")

# ---------------------------------------------------------------- 4. etapas
p("\n## 4. Efeito de cada mudança, em sequência\n")
etapas = [("v1.0 publicada", {}),
          ("+ correções de leitura (consórcio; linha (I) omitida = 0)", dict(leitura=True)),
          ("+ teto da autonomia 10 → 7", dict(leitura=True, teto_aut=7.0)),
          ("+ transparência como multiplicador (= v1.1 proposta)", dict(leitura=True, teto_aut=7.0, transp="multiplica"))]
p("| Etapa | com nota | 0–2 / 2–4 / 4–6 / 6–8 / 8–10 | mín | mediana | máx | desvio |\n|---|---|---|---|---|---|---|")
RES = []
for rot, kw in etapas:
    d = VAL(**kw)
    RES.append((rot, d))
    n, f, mn, md, mx, dp = resumo(d)
    p(f"| {rot} | {n} | {' / '.join(map(str,f))} | {br(mn)} | {br(md)} | {br(mx)} | {br(dp,2)} |")

v10, v11 = RES[0][1], RES[-1][1]
r10, r11 = ranking(v10), ranking(v11)
p(f"\nCorrelação de posições (Spearman) v1.0 × v1.1: {br(spearman(v10, v11),3)}.")


def tabela(cods, titulo):
    p(f"\n### {titulo}\n\n| v1.1 | Município | Nota v1.1 | Nota v1.0 | Posição v1.0 | Variação |\n|---|---|---|---|---|---|")
    for c in cods:
        d = (r10.get(c) or 0) - r11[c] if c in r10 else None
        p(f"| {r11[c]} | {NOME[c]} | {br(v11[c]*10)} | {br(v10[c]*10) if v10[c] is not None else 'sem nota'} | {r10.get(c,'—')} | {('+' if d and d>0 else '')+str(d) if d is not None else 'nova'} |")


ordem = sorted(r11, key=lambda c: r11[c])
tabela(ordem[:20], "Os 20 primeiros na v1.1")
tabela(ordem[-20:], "Os 20 últimos na v1.1")

# motivo: a etapa que mais moveu a posição
rks = [ranking(d) for _, d in RES]
mov = []
for c in r11:
    if c not in r10:
        mov.append((10**6, c, "passa a ter nota com a correção de leitura"))
        continue
    curto = ["leitura", "teto da autonomia", "transparência"]
    passos = [(rks[i][c] - rks[i + 1][c], curto[i]) for i in range(len(etapas) - 1)]
    motivo = "; ".join(f"{r} {'+' if d > 0 else ''}{d}" for d, r in passos if abs(d) >= 5)
    mov.append((r10[c] - r11[c], c, motivo))
mov.sort(key=lambda x: -abs(x[0]))
p("\n### Os 20 que mais mudam de posição\n\n| Município | Posição v1.0 → v1.1 | Variação | Nota v1.0 → v1.1 | Contribuição de cada etapa (posições) |\n|---|---|---|---|---|")
for d, c, mot in mov[:20]:
    p(f"| {NOME[c]} | {r10.get(c,'sem nota')} → {r11[c]} | {('+' if d>0 else '')+str(d) if d < 10**6 else 'nova'} | {br(v10[c]*10) if v10[c] is not None else 'sem nota'} → {br(v11[c]*10)} | {mot} |")
# alternativa não recomendada: pessoal acima de 100% da RCL fora da nota
alt = VAL(leitura=True, teto_aut=7.0, transp="multiplica", pessoal_max=100.0)
ra = ranking(alt)
ganhos = sorted(((r11[c] - ra[c], c) for c in ra), reverse=True)[:5]
p("\n### Alternativa não recomendada: pessoal acima de 100% da RCL fora da nota\n")
p("Maiores ganhos de posição em relação à v1.1 proposta: " + "; ".join(f"{NOME[c]} (+{d})" for d, c in ganhos) + ".")
open(AQUI + "/simulacao.md", "w").write("\n".join(out))
print("\n".join(out))
