"""Qual commit do `main` está rodando, mesmo sem o histórico do Git.

O deployment do Replit não traz a pasta `.git`: ele só muda com Pull + Republish, e um
Republish esquecido faz a coleta rodar código antigo (08/10/2026, duas vezes). No início
de cada coleta, `rastro conferir-codigo` compara o código em disco com os últimos commits
do `main` no GitHub:

- calcula o hash Git (blob SHA-1) de cada arquivo de `backend/` e `frontend/` (o código
  que roda; commits só de documentação não pedem Republish);
- busca, pela API do GitHub, a árvore de cada um dos últimos commits do `main`;
- o commit mais recente com o mesmo código é o publicado.

Imprime no log o commit publicado e o do `main` e, se o publicado estiver atrás, um AVISO
para fazer Pull + Republish. Nunca interrompe a coleta: se não conseguir conferir, avisa e
segue. Na saída padrão fica só o hash do commit publicado (ou nada), para o manifesto.
"""

import hashlib
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

REPO = "fasn98/rastro-publico"
API = "https://api.github.com"
PASTAS = ("backend/", "frontend/")
ULTIMOS = 30


def blob_sha(conteudo: bytes) -> str:
    """O mesmo hash que o Git dá a um arquivo (`git hash-object`)."""
    return hashlib.sha1(b"blob %d\0" % len(conteudo) + conteudo).hexdigest()


def arvore_local(raiz: Path, caminhos: Iterable[str]) -> dict[str, str | None]:
    """{caminho: hash} dos arquivos pedidos; None se o arquivo não existe no disco."""
    saida = {}
    for c in caminhos:
        p = raiz / c
        saida[c] = blob_sha(p.read_bytes()) if p.is_file() else None
    return saida


@dataclass
class Commit:
    sha: str
    data: str
    # {caminho: hash} dos arquivos de PASTAS nesse commit
    arquivos: dict[str, str]


@dataclass
class Resultado:
    publicado: Commit | None
    main: Commit
    atras: int | None  # commits de código entre o publicado e o main; None = desconhecido
    diferentes: int  # arquivos que não batem com o main


def comparar(raiz: Path, commits: list[Commit]) -> Resultado:
    """`commits`: do mais recente (o main) para o mais antigo."""
    main = commits[0]
    publicado = None
    distintos = []  # versões de código distintas, do main para trás
    for c in commits:
        if not distintos or c.arquivos != distintos[-1].arquivos:
            distintos.append(c)
        local = arvore_local(raiz, c.arquivos)
        if local == c.arquivos:
            publicado = c
            break
    local_main = arvore_local(raiz, main.arquivos)
    diferentes = sum(1 for k, v in main.arquivos.items() if local_main[k] != v)
    atras = len(distintos) - 1 if publicado else None
    return Resultado(publicado, main, atras, diferentes)


def commits_do_github(client: httpx.Client, quantos: int = ULTIMOS) -> list[Commit]:
    """Últimos commits do main com a árvore de PASTAS (API pública do GitHub)."""
    r = client.get(f"{API}/repos/{REPO}/commits", params={"sha": "main", "per_page": quantos})
    r.raise_for_status()
    saida = []
    for item in r.json():
        arvore = client.get(
            f"{API}/repos/{REPO}/git/trees/{item['commit']['tree']['sha']}",
            params={"recursive": "1"},
        )
        arvore.raise_for_status()
        dados = arvore.json()
        if dados.get("truncated"):
            raise RuntimeError("árvore do commit truncada pela API do GitHub")
        saida.append(
            Commit(
                sha=item["sha"],
                data=item["commit"]["committer"]["date"],
                arquivos={
                    e["path"]: e["sha"]
                    for e in dados["tree"]
                    if e["type"] == "blob" and e["path"].startswith(PASTAS)
                },
            )
        )
    return saida


def mensagem(r: Resultado) -> str:
    main = f"main {r.main.sha[:7]} ({r.main.data[:10]})"
    if r.publicado is None:
        return (
            f"AVISO: o código publicado não corresponde a nenhum dos últimos {ULTIMOS} commits "
            f"do main ({main}; {r.diferentes} arquivo(s) diferentes). Faça Pull + Republish "
            "no Replit."
        )
    pub = f"{r.publicado.sha[:7]} ({r.publicado.data[:10]})"
    if r.atras == 0:
        return f"Código publicado em dia: {pub}, mesmo código do {main}."
    return (
        f"AVISO: o código publicado ({pub}) está {r.atras} versão(ões) de código atrás do "
        f"{main}. Esta coleta roda o código antigo. Faça Pull + Republish no Replit."
    )


def conferir(
    raiz: Path, novo_cliente: Callable[[], httpx.Client], avisar: Callable[[str], None]
) -> str | None:
    """Confere e avisa; devolve o hash do commit publicado, ou None se não souber."""
    try:
        with novo_cliente() as client:
            commits = commits_do_github(client)
        r = comparar(raiz, commits)
    except Exception as exc:  # a conferência nunca derruba a coleta
        avisar(f"AVISO: não foi possível conferir a versão do código ({type(exc).__name__}: {exc})")
        return None
    avisar(mensagem(r))
    return r.publicado.sha if r.publicado else None
