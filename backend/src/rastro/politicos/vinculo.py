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
4. todas as emendas ligadas a ele têm o mesmo "Código do Autor";
5. a UF do parlamentar está publicada: a UF da exportação (SP) ou uma UF de
   `RASTRO_POL_UFS_LIBERADAS` (decisão do Fabio, 17/11/2026). Uma UF coletada e ainda não
   liberada (ex.: RS na conferência antes da liberação) não grava vínculo nenhum: as
   emendas dos autores dela aparecem como na fonte, sem link, como já aparecem hoje. Sem
   isso, a página de um município publicado ligaria a uma página de político que o site não
   exporta, e a verificação antes de publicar barraria o site inteiro.

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

from rastro.config import get_settings
from rastro.politicos import camara, lgpd, senado
from rastro.politicos.comum import get_json_com_origem
from rastro.politicos.modelos import DEPUTADO_FEDERAL, SENADOR, PolPolitico
from rastro.politicos.transparencia import normalizar_nome

# UF da exportação: os políticos dela estão sempre no site (`rastro exportar-site --uf SP`)
UF_EXPORTACAO = "SP"
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


def ufs_publicadas() -> set[str]:
    """UFs cujos políticos o site publica: a da exportação e as liberadas pelo Fabio."""
    return {UF_EXPORTACAO} | get_settings().ufs_liberadas


def ufs_com_vinculo(ufs) -> list[str]:
    """Regra 5: das UFs coletadas, só as publicadas gravam vínculo com o autor."""
    return sorted({u.upper() for u in ufs} & ufs_publicadas())


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


def excecoes_por_texto(
    session: Session, ufs: set[str] | None = None
) -> dict[str, tuple[int | None, str]]:
    """Texto exato do autor na fonte -> (pol_politico.id, rótulo), para as exceções.

    `ufs`: UFs que gravam vínculo (regra 5). A exceção de político de outra UF continua na
    lista, com o id nulo: a linha entra no recorte do arquivo (o portão confere que ela
    existe) e fica sem vínculo até a UF ser liberada. Sem `ufs`, todas com o id."""
    linhas = session.execute(
        select(PolPolitico.id_fonte, PolPolitico.id, PolPolitico.uf).where(
            PolPolitico.fonte == "camara"
        )
    ).all()
    ids = {id_fonte: (pid, uf) for id_fonte, pid, uf in linhas}
    saida = {}
    for e in carregar_excecoes():
        achado = ids.get(str(e["camara_id"]))
        if achado is None:
            continue
        pid, uf = achado
        saida[e["texto_fonte"]] = (pid if ufs is None or uf in ufs else None, e["rotulo"])
    return saida
