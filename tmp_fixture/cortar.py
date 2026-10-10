"""Corta as amostras reais de deputado distrital do DF (TSE 2022 e 2026), sem colunas pessoais.

Branch temporário: só grava a fixture como artefato do Actions; o branch é apagado depois.
"""

import csv
import io
import sys
import urllib.request
import zipfile

URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_{ano}.zip"
PESSOAIS = {
    "NM_CANDIDATO", "NM_SOCIAL_CANDIDATO", "NR_CPF_CANDIDATO", "DS_EMAIL", "SG_UF_NASCIMENTO",
    "DT_NASCIMENTO", "NR_TITULO_ELEITORAL_CANDIDATO", "CD_GENERO", "DS_GENERO",
    "CD_GRAU_INSTRUCAO", "DS_GRAU_INSTRUCAO", "CD_ESTADO_CIVIL", "DS_ESTADO_CIVIL",
    "CD_COR_RACA", "DS_COR_RACA", "CD_OCUPACAO", "DS_OCUPACAO",
}
ELEITO = {"ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA"}

for ano in (2022, 2026):
    dados = urllib.request.urlopen(URL.format(ano=ano), timeout=600).read()
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        texto = z.read(f"consulta_cand_{ano}_DF.csv").decode("latin-1")
    linhas = list(csv.DictReader(io.StringIO(texto), delimiter=";"))
    colunas = [c for c in linhas[0] if c not in PESSOAIS]
    distritais = [r for r in linhas if r["DS_CARGO"] == "DEPUTADO DISTRITAL"]
    eleitos = [r for r in distritais if r["DS_SIT_TOT_TURNO"] in ELEITO]
    outros = [r for r in distritais if r["DS_SIT_TOT_TURNO"] not in ELEITO][:6]
    print(ano, "distritais:", len(distritais), "eleitos:", len(eleitos),
          "situações:", sorted({r["DS_SIT_TOT_TURNO"] for r in distritais}),
          "CD_CARGO:", sorted({r["CD_CARGO"] for r in distritais}), file=sys.stderr)
    with open(f"tse_consulta_cand_{ano}_DF_distritais.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, colunas, delimiter=";", quoting=csv.QUOTE_ALL,
                           lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for r in eleitos + outros:
            w.writerow(r)
