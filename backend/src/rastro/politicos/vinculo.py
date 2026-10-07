"""Vínculo confirmado entre o autor de uma emenda e um parlamentar do portal.

O arquivo de emendas identifica o autor por nome e por um código próprio ("Código do
Autor"), sem identificador da Câmara ou do Senado nem UF. Uma emenda só é ligada à
página de um político quando, sem ambiguidade:

1. o nome do autor (sem o sufixo "(EX-PARLAMENTAR ...)") é igual, depois de normalizado,
   ao nome de exatamente UM parlamentar federal da legislatura, de qualquer UF
   (Câmara e Senado; quem tem o mesmo nome de outro parlamentar não é ligado);
2. esse parlamentar é um dos da UF no portal;
3. o ano da emenda cai no mandato: o orçamento do ano Y é votado no ano Y-1, então o
   parlamentar precisa ter mandato em Y-1;
4. todas as emendas ligadas a ele têm o mesmo "Código do Autor".

Nos demais casos a emenda aparece com o autor exatamente como está na fonte, sem link.

Exceções aprovadas uma a uma pelo mantenedor ficam em `excecoes_emendas.toml` (versionado,
com justificativa); a emenda é ligada ao político indicado e exibida com um rótulo.
"""

import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from rastro.politicos import camara, lgpd, senado
from rastro.politicos.comum import get_json_com_origem
from rastro.politicos.modelos import DEPUTADO_FEDERAL, SENADOR, PolPolitico
from rastro.politicos.transparencia import normalizar_nome

LEGISLATURA = 57
ANOS_LEGISLATURA = {57: (2023, 2026)}  # anos civis em que a legislatura 57 vota orçamentos


@dataclass(frozen=True)
class Autor:
    politico_id: int
    nome: str
    primeiro_ano: int  # primeiro "Ano da Emenda" coberto pelo mandato
    ultimo_ano: int


def universo(client: httpx.Client, legislatura: int = LEGISLATURA) -> dict[str, set[str]]:
    """Nome normalizado -> identificadores ("camara:ID" / "senado:COD") na legislatura."""
    nomes: dict[str, set[str]] = defaultdict(set)
    params = {"idLegislatura": legislatura, "itens": 100, "ordem": "ASC", "ordenarPor": "nome"}
    for itens, _ in camara.paginas(
        client, f"{camara.API}/deputados", params, lgpd.CAMARA_DEPUTADOS
    ):
        for d in itens:
            nomes[normalizar_nome(d["nome"])].add(f"camara:{d['id']}")
    url = f"{senado.API}/senador/lista/legislatura/{legislatura}.json"
    dados, _ = get_json_com_origem(client, url, redator=lgpd.SENADO_LISTA)
    lista = dados["ListaParlamentarLegislatura"]["Parlamentares"]["Parlamentar"]
    for p in senado._lista(lista):
        ident = p["IdentificacaoParlamentar"]
        nomes[normalizar_nome(ident["NomeParlamentar"])].add(f"senado:{ident['CodigoParlamentar']}")
    return nomes


def autores_confirmaveis(
    session: Session, uf: str, nomes: dict[str, set[str]]
) -> tuple[dict[str, Autor], dict[str, str]]:
    """Autores da UF que passam nas regras 1 e 2; e os que não passam, com o motivo."""
    autores, recusados = {}, {}
    for p in session.scalars(
        select(PolPolitico).where(
            PolPolitico.uf == uf,
            PolPolitico.fonte.in_(["camara", "senado"]),
            PolPolitico.cargo.in_([DEPUTADO_FEDERAL, SENADOR]),
        )
    ):
        chave = normalizar_nome(p.nome)
        ids = nomes.get(chave, set())
        meu = f"{p.fonte}:{p.id_fonte}"
        if ids != {meu}:
            recusados[p.nome] = (
                f"nome igual ao de outro parlamentar: {sorted(ids - {meu})}"
                if len(ids) > 1
                else "não encontrado na lista da legislatura"
            )
            continue
        if p.fonte == "senado" and p.mandato_inicio and p.mandato_fim:
            inicio, fim = p.mandato_inicio.year, p.mandato_fim.year - 1
        else:
            inicio, fim = ANOS_LEGISLATURA[p.legislatura or LEGISLATURA]
        autores[chave] = Autor(p.id, p.nome, inicio + 1, fim + 1)
    return autores, recusados


ARQUIVO_EXCECOES = Path(__file__).with_name("excecoes_emendas.toml")


def carregar_excecoes(caminho: Path = ARQUIVO_EXCECOES) -> list[dict]:
    with caminho.open("rb") as f:
        return tomllib.load(f).get("excecao", [])


def excecoes_por_texto(session: Session) -> dict[str, tuple[int, str]]:
    """Texto exato do autor na fonte -> (pol_politico.id, rótulo), para as exceções."""
    ids = dict(
        session.execute(
            select(PolPolitico.id_fonte, PolPolitico.id).where(PolPolitico.fonte == "camara")
        ).all()
    )
    saida = {}
    for e in carregar_excecoes():
        pid = ids.get(str(e["camara_id"]))
        if pid is not None:
            saida[e["texto_fonte"]] = (pid, e["rotulo"])
    return saida
