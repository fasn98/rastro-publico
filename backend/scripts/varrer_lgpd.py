"""Varredura LGPD: procura CPF, e-mail e telefone no banco e no arquivo de respostas brutas.

Só leitura. Imprime fonte, campo e quantidade, nunca os valores encontrados.

    cd backend && uv run python scripts/varrer_lgpd.py [--sem-arquivo] [--json saida.json]

- Banco: toda coluna de texto (text/varchar) de todas as tabelas do schema public. Nas
  tabelas de políticos, a fonte vem do político (Câmara, Senado, TSE).
- Arquivo bruto: cada conteúdo de `payload_bruto` (os bytes gravados, já redigidos quando
  há redação), aberto como JSON (por chave), CSV (por coluna, também dentro de ZIP) ou,
  se não for nenhum dos dois, como texto inteiro ("(conteúdo)"). A fonte vem do endereço.

Padrões (contados por ocorrência; "linhas" = linhas do banco ou conteúdos do arquivo). O
dígito verificador é o da regra do CPF, a mesma da redação (`lgpd.cpf_valido`: dígitos
iguais, como "00000000000", não são CPF):
- cpf_formatado_dv_valido / cpf_formatado_dv_invalido: 11 dígitos com pontuação, completa
  (000.000.000-00) ou parcial (000000000-00, 000.000.00000);
- cpf_11_digitos_dv_valido / 11_digitos_dv_invalido: 11 dígitos seguidos, sem pontuação;
- email_institucional (.gov.br, .leg.br, .jus.br, .mp.br, .def.br) e email_outro;
- telefone: (00) 0000-0000, (00) 00000-0000, +55..., 0800 000 0000.

Campos que são identificador, hash, código ou link (sha256, id_fonte, url_pagina,
SQ_CANDIDATO, urlDocumento...) saem numa seção à parte: os 11 dígitos neles são parte do
identificador, não dado pessoal em texto.
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
from rastro.politicos.lgpd import cpf_valido

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


# nome do campo (sem a tabela ou o prefixo "zip:"), em minúsculas
_IDENTIFICADOR = re.compile(
    r"sha256\w*|hash\w*|id|id_\w+|\w+_id|\w*_id[a-z]\w*|ide_?(cadastro|documento)"
    r"|uri\w*|\w*_uri\w*|url\w*|\w*_url\w*|sq_\w+|cod(igo)?\w*|\w+_cod\w*"
)


# camelCase com "id" na frente (idOrgao, idEvento, idDeputadoAutor): pelo nome original,
# porque em minúsculas "identificacao" ficaria igual a um id
_ID_CAMEL = re.compile(r"ide?[A-Z]\w*")


def identificador(campo: str) -> bool:
    """Campo que é identificador, hash, código ou link, não texto."""
    nome = re.split(r"[.:]", campo)[-1]
    return bool(_ID_CAMEL.fullmatch(nome) or _IDENTIFICADOR.fullmatch(nome.lower()))


def achados(valor: str) -> dict[str, int]:
    r: dict[str, int] = {}

    def soma(chave, n):
        if n:
            r[chave] = r.get(chave, 0) + n

    for m in CPF_PONTUADO.findall(valor):
        if not m.isdigit():
            soma("cpf_formatado_dv_" + ("valido" if cpf_valido(m) else "invalido"), 1)
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
            {
                "fonte": f,
                "campo": c,
                "padrao": p,
                "linhas": n[0],
                "ocorrencias": n[1],
                "identificador": identificador(c),
            }
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


def varrer_arquivo(session, cont: Contagem) -> tuple[int, int]:
    """Devolve (conteúdos lidos, total de linhas de payload_bruto)."""
    total = session.execute(text("select count(*) from payload_bruto")).scalar_one()
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
    return n, total


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sem-arquivo", action="store_true", help="só o banco")
    ap.add_argument("--json", help="grava também o resultado neste arquivo")
    args = ap.parse_args(argv)
    cont = Contagem()
    with get_sessionmaker()() as session:
        varrer_banco(session, cont)
        lidos, total = (None, None) if args.sem_arquivo else varrer_arquivo(session, cont)
    linhas = cont.linhas()
    if args.sem_arquivo:
        print("Arquivo bruto: não varrido (--sem-arquivo)")
    else:
        print(f"Arquivo bruto: {lidos} de {total} conteúdos de payload_bruto lidos")
    for titulo, ident in (
        ("TEXTO", False),
        ("IDENTIFICADORES, HASHES, CÓDIGOS E LINKS (não é texto: ruído do padrão)", True),
    ):
        print(f"\n== {titulo}")
        print(f"{'fonte':42} {'campo':45} {'padrão':26} {'linhas':>7} {'ocorr.':>7}")
        for x in (x for x in linhas if x["identificador"] == ident):
            print(
                f"{x['fonte']:42} {x['campo']:45} {x['padrao']:26} "
                f"{x['linhas']:>7} {x['ocorrencias']:>7}"
            )
    if args.json:
        arquivo = {"varrido": not args.sem_arquivo, "lidos": lidos, "total": total}
        with open(args.json, "w") as f:
            json.dump({"arquivo": arquivo, "achados": linhas}, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
