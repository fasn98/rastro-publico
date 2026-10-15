"""Varredura LGPD: procura CPF, e-mail e telefone no banco e no arquivo de respostas brutas.

Só leitura. Imprime fonte, campo e quantidade, nunca os valores encontrados.

    cd backend && uv run python scripts/varrer_lgpd.py [--sem-arquivo] [--json saida.json]

- Banco: toda coluna de texto (text/varchar) de todas as tabelas do schema public. Nas
  tabelas de políticos, a fonte vem do político (Câmara, Senado, TSE).
- Arquivo bruto: cada conteúdo de `payload_bruto` (os bytes gravados, já redigidos quando
  há redação), aberto como JSON (por chave), CSV (por coluna, também dentro de ZIP) ou,
  se não for nenhum dos dois, como texto inteiro ("(conteúdo)"). A fonte vem do endereço.

Padrões (contados por ocorrência; "linhas" = linhas do banco ou conteúdos do arquivo):
- cpf_formatado: 000.000.000-00, também com pontuação parcial (000000000-00, 000.000.00000);
- cpf_11_digitos_dv_valido: 11 dígitos seguidos, com dígitos verificadores de CPF válidos;
- 11_digitos_dv_invalido: 11 dígitos seguidos que não passam no dígito verificador
  (não são CPF; aparecem para mostrar o ruído do padrão);
- email_institucional (.gov.br, .leg.br, .jus.br, .mp.br, .def.br) e email_outro;
- telefone: (00) 0000-0000, (00) 00000-0000, +55..., 0800 000 0000.
"""

import argparse
import csv
import gzip
import io
import json
import re
import sys
import zipfile
from collections import defaultdict

from sqlalchemy import text

from rastro.db import get_sessionmaker

csv.field_size_limit(sys.maxsize)

# 11 dígitos com pontuação completa ou parcial; os sem pontuação ficam com ONZE
CPF_PONTUADO = re.compile(r"(?<!\d)(?<!\d\.)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
ONZE = re.compile(r"(?<![\d.,/-])\d{11}(?![\d])")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
INSTITUCIONAL = re.compile(r"\.(gov|leg|jus|mp|def)\.br$", re.I)
TELEFONE = re.compile(
    r"(?:\+55\s?)?\(\d{2}\)\s?9?\d{4}[-\s]?\d{4}(?!\d)"
    r"|(?<!\d)\+55\s?\d{2}\s?9?\d{4}[-\s]?\d{4}(?!\d)"
    r"|(?<!\d)0800[\s-]?\d{3}[\s-]?\d{4}(?!\d)"
)

FONTES = {
    "dadosabertos.camara.leg.br": "Câmara",
    "www.camara.leg.br": "Câmara",
    "legis.senado.leg.br": "Senado",
    "cdn.tse.jus.br": "TSE",
    "dadosabertos.tse.jus.br": "TSE",
    "apidatalake.tesouro.gov.br": "SICONFI",
    "portaldatransparencia.gov.br": "Emendas (Portal da Transparência)",
    "api.portaldatransparencia.gov.br": "Emendas (Portal da Transparência)",
    "dadosabertos-download.cgu.gov.br": "Emendas (Portal da Transparência)",
    "servicodados.ibge.gov.br": "IBGE",
}


def cpf_valido(d: str) -> bool:
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10) % 11 % 10 != int(d[n]):
            return False
    return True


def achados(valor: str) -> dict[str, int]:
    r: dict[str, int] = {}

    def soma(chave, n):
        if n:
            r[chave] = r.get(chave, 0) + n

    soma("cpf_formatado", sum(not m.isdigit() for m in CPF_PONTUADO.findall(valor)))
    for m in ONZE.finditer(valor):
        soma("cpf_11_digitos_dv_valido" if cpf_valido(m.group()) else "11_digitos_dv_invalido", 1)
    for m in EMAIL.finditer(valor):
        dominio = m.group().rsplit("@", 1)[1]
        soma("email_institucional" if INSTITUCIONAL.search(dominio) else "email_outro", 1)
    soma("telefone", len(TELEFONE.findall(valor)))
    return r


class Contagem:
    def __init__(self):
        # (fonte, campo, padrão) -> [linhas, ocorrências]
        self.c: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0])

    def valor(self, fonte: str, campo: str, valor) -> None:
        if not isinstance(valor, str) or len(valor) < 8:
            return
        for padrao, n in achados(valor).items():
            x = self.c[(fonte, campo, padrao)]
            x[0] += 1
            x[1] += n

    def linhas(self) -> list[dict]:
        return [
            {"fonte": f, "campo": c, "padrao": p, "linhas": n[0], "ocorrencias": n[1]}
            for (f, c, p), n in sorted(self.c.items())
        ]


# ------------------------------------------------------------------------------ banco


def varrer_banco(session, cont: Contagem) -> None:
    colunas = session.execute(
        text(
            "select c.table_name, c.column_name from information_schema.columns c "
            "join information_schema.tables t on t.table_name = c.table_name "
            "and t.table_schema = c.table_schema "
            "where c.table_schema = 'public' and t.table_type = 'BASE TABLE' "
            "and c.data_type in ('text', 'character varying') "
            "and c.table_name <> 'alembic_version' order by 1, 2"
        )
    ).all()
    com_politico = {
        t
        for (t,) in session.execute(
            text(
                "select table_name from information_schema.columns "
                "where table_schema = 'public' and column_name = 'politico_id'"
            )
        )
    }
    for tabela, coluna in colunas:
        if tabela in com_politico:
            sql = (
                f'select p.fonte, t."{coluna}" from "{tabela}" t '
                f'join pol_politico p on p.id = t.politico_id where t."{coluna}" is not null'
            )
        elif tabela == "pol_politico":
            sql = f'select fonte, "{coluna}" from pol_politico where "{coluna}" is not null'
        else:
            sql = f'select null, "{coluna}" from "{tabela}" where "{coluna}" is not null'
        for fonte, valor in session.execute(text(sql)).yield_per(5000):
            cont.valor(f"banco/{fonte or tabela.split('_')[0]}", f"{tabela}.{coluna}", valor)


# ---------------------------------------------------------------------- arquivo bruto


def _texto(b: bytes) -> str:
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


def _json(cont: Contagem, fonte: str, no, chave: str = "(raiz)") -> None:
    if isinstance(no, dict):
        for k, v in no.items():
            _json(cont, fonte, v, k)
    elif isinstance(no, list):
        for v in no:
            _json(cont, fonte, v, chave)
    else:
        cont.valor(fonte, chave, no)


def _csv(cont: Contagem, fonte: str, texto: str, prefixo: str = "") -> bool:
    primeira = texto.split("\n", 1)[0]
    delim = max((";", ",", "\t"), key=primeira.count)
    if primeira.count(delim) < 1:
        return False
    for linha in csv.DictReader(io.StringIO(texto), delimiter=delim):
        for k, v in linha.items():
            cont.valor(fonte, f"{prefixo}{k}", v)
    return True


def varrer_conteudo(cont: Contagem, fonte: str, dados: bytes) -> None:
    if dados[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(dados)) as z:
            for nome in z.namelist():
                if nome.lower().endswith((".csv", ".txt")):
                    _csv(cont, fonte, _texto(z.read(nome)), "zip:")
        return
    t = _texto(dados)
    inicio = t.lstrip()[:1]
    if inicio in ("{", "["):
        try:
            _json(cont, fonte, json.loads(t))
            return
        except ValueError:
            pass
    if inicio != "<" and _csv(cont, fonte, t):
        return
    cont.valor(fonte, "(conteúdo)", t)


def varrer_arquivo(session, cont: Contagem) -> int:
    hosts = dict(
        session.execute(
            text(
                "select distinct on (sha256) sha256, split_part(url, '/', 3) "
                "from resposta_bruta order by sha256, id"
            )
        ).all()
    )
    n = 0
    rows = session.execute(
        text("select sha256, compressao, conteudo from payload_bruto order by sha256")
    ).yield_per(50)
    for sha, compressao, conteudo in rows:
        dados = gzip.decompress(conteudo) if compressao == "gzip" else bytes(conteudo)
        host = hosts.get(sha, "?")
        varrer_conteudo(cont, f"arquivo/{FONTES.get(host, host)}", dados)
        n += 1
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sem-arquivo", action="store_true", help="só o banco")
    ap.add_argument("--json", help="grava também o resultado neste arquivo")
    args = ap.parse_args(argv)
    cont = Contagem()
    with get_sessionmaker()() as session:
        varrer_banco(session, cont)
        n = 0 if args.sem_arquivo else varrer_arquivo(session, cont)
    linhas = cont.linhas()
    print(f"Conteúdos do arquivo bruto lidos: {n}")
    print(f"{'fonte':42} {'campo':45} {'padrão':26} {'linhas':>7} {'ocorr.':>7}")
    for x in linhas:
        print(
            f"{x['fonte']:42} {x['campo']:45} {x['padrao']:26} "
            f"{x['linhas']:>7} {x['ocorrencias']:>7}"
        )
    if args.json:
        with open(args.json, "w") as f:
            json.dump({"conteudos_lidos": n, "achados": linhas}, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
