"""Saídas de políticos do site: só com aprovação (ADR-0026, decisão do Fabio, 21/11/2026).

Antes de publicar, a verificação compara os políticos do site publicado com os da nova
versão pelo par (fonte, id_fonte), e não só pela contagem. Toda saída, mesmo com a
contagem igual ou maior, só passa se estiver em `remocoes_aprovadas.toml`; qualquer outra
barra a publicação. Quem entrou e quem saiu vai sempre para o resumo da execução, mesmo
quando a publicação passa.

Os políticos de uma versão do site vêm de dois conjuntos de arquivos, que juntos cobrem
todos os políticos contados no manifesto (`contagens.politicos`):

- `politicos/{id}.json`: deputados federais e senadores (Câmara e Senado);
- `eleitos/*.json`: eleitos do TSE (`m-{cod_ibge}` por município, `uf-{UF}-{ano}` por UF).
"""

import json
import re
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path

ARQUIVO = Path(__file__).with_name("remocoes_aprovadas.toml")
CAMPOS = (
    "fonte",
    "id_fonte",
    "nome",
    "cargo",
    "municipio",
    "situacao_no_arquivo",
    "arquivo_fonte",
    "base",
    "valida_ate",
    "aprovado_em",
    "aprovado_por",
)

Chave = tuple[str, str]  # (fonte, id_fonte)


class ListaInvalida(ValueError):
    pass


def carregar(caminho: Path | None = None) -> dict[Chave, dict]:
    """{(fonte, id_fonte): entrada} da lista de remoções aprovadas."""
    with open(caminho or ARQUIVO, "rb") as f:
        entradas = tomllib.load(f).get("remocao", [])
    saida: dict[Chave, dict] = {}
    for i, e in enumerate(entradas, 1):
        faltando = [c for c in CAMPOS if not e.get(c)]
        if faltando:
            raise ListaInvalida(f"remoção {i} sem {', '.join(faltando)}")
        if not re.fullmatch(r"site-\d{8}-\d{6}", str(e["base"])):
            raise ListaInvalida(f"remoção {i}: base fora do formato site-AAAAMMDD-HHMMSS")
        if not isinstance(e["valida_ate"], date):
            raise ListaInvalida(f"remoção {i}: valida_ate não é uma data")
        chave = (str(e["fonte"]), str(e["id_fonte"]))
        if chave in saida:
            raise ListaInvalida(f"remoção repetida: {chave[0]} {chave[1]}")
        saida[chave] = e
    return saida


def _expandir(d: dict) -> list[dict]:
    """Itens completos de um arquivo no formato de `site.compactar` (comum + índices)."""
    comum = d.get("comum", {})
    indices = d.get("indices", {})
    saida = []
    for it in d.get("itens", []):
        x = {**comum, **it}
        for campo, valores in indices.items():
            if isinstance(x.get(campo), int):
                x[campo] = valores[x[campo]]
        saida.append(x)
    return saida


def _nomes_municipios(dados: Path) -> dict[int, str]:
    """{cod_ibge: "Nome/UF"} pela busca nacional (todas as UFs no site) ou, sem ela, pela
    lista de municípios da UF da exportação."""
    nomes: dict[int, str] = {}
    busca = dados / "busca.json"
    if busca.exists():
        for i in _expandir(json.loads(busca.read_bytes())):
            if i.get("tipo") == "municipio":
                nomes[i["cod_ibge"]] = f"{i['nome']}/{i['uf']}"
    lista = dados / "municipios.json"
    if lista.exists():
        for m in json.loads(lista.read_bytes()):
            nomes.setdefault(m["cod_ibge"], f"{m['nome']}/{m.get('uf', '')}")
    return nomes


def politicos_do_site(dados: Path) -> dict[Chave, dict]:
    """{(fonte, id_fonte): {nome, cargo, local}} dos políticos de uma versão do site."""
    nomes = _nomes_municipios(dados)
    saida: dict[Chave, dict] = {}
    for arq in sorted((dados / "politicos").glob("*.json")):
        p = json.loads(arq.read_bytes())
        saida[(p["fonte"], str(p["id_fonte"]))] = {
            "nome": p["nome"],
            "cargo": p["cargo"],
            "local": p.get("uf") or "",
        }
    for arq in sorted((dados / "eleitos").glob("*.json")):
        for it in _expandir(json.loads(arq.read_bytes())):
            cod = it.get("cod_ibge")
            saida[(it.get("fonte", "tse"), str(it["id_fonte"]))] = {
                "nome": it["nome"],
                "cargo": it.get("cargo"),
                "local": nomes.get(cod, str(cod)) if cod else it.get("uf", ""),
            }
    return saida


def comparar(
    antes: dict[Chave, dict],
    agora: dict[Chave, dict],
    aprovadas: dict,
    base: str | None,
    hoje: date | None = None,
) -> dict:
    """Quem entrou, quem saiu e quem saiu sem aprovação, em ordem de fonte e id_fonte.

    `base` é a publicação no ar (tag `site-AAAAMMDD-HHMMSS`). Uma entrada da lista só
    libera a saída quando a publicação no ar é a `base` dela ou uma posterior (as tags têm
    data e hora, e a ordem delas é a ordem do texto) e `hoje` não passou de `valida_ate`
    (decisão do Fabio, 23/11/2026). Fora disso, ou sem publicação no ar conhecida, a saída
    conta como sem aprovação.
    """
    hoje = hoje or datetime.now(UTC).date()

    def ordenar(chaves):
        return sorted(chaves, key=lambda k: (k[0], k[1]))

    def aprovada(k: Chave) -> bool:
        e = aprovadas.get(k)
        return base is not None and e is not None and base >= e["base"] and hoje <= e["valida_ate"]

    entraram = ordenar(set(agora) - set(antes))
    sairam = ordenar(set(antes) - set(agora))
    return {
        "entraram": [(k, agora[k]) for k in entraram],
        "sairam": [(k, antes[k]) for k in sairam],
        "sem_aprovacao": [(k, antes[k]) for k in sairam if not aprovada(k)],
    }


def _linha(chave: Chave, p: dict) -> str:
    return f"{p['nome']} ({p['cargo']}, {p['local']}; {chave[0]} {chave[1]})"


def problemas(diff: dict) -> list[str]:
    return [
        f"político saiu sem aprovação em remocoes_aprovadas.toml: {_linha(k, p)}"
        for k, p in diff["sem_aprovacao"]
    ]


def resumo(diff: dict) -> list[str]:
    """Linhas do resumo da execução: sempre, mesmo sem mudança."""
    linhas = [f"Políticos: {len(diff['entraram'])} entraram, {len(diff['sairam'])} saíram"]
    linhas += [f"  entrou: {_linha(k, p)}" for k, p in diff["entraram"]]
    sem = {k for k, _ in diff["sem_aprovacao"]}
    linhas += [
        f"  saiu ({'SEM APROVAÇÃO' if k in sem else 'aprovada'}): {_linha(k, p)}"
        for k, p in diff["sairam"]
    ]
    return linhas
