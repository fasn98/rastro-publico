"""Publicação do site estático no GitHub Pages (branch `gh-pages`), com reversão.

Cada publicação é um commit sem histórico no `gh-pages` (o site inteiro, substituído de
uma vez) e uma tag `site-AAAAMMDD-HHMMSS` apontando para ele. As tags guardam as últimas
`MANTER` publicações; `reverter` volta o `gh-pages` para qualquer uma delas.

O `main` não é tocado: ele só recebe mudanças por pull request.

Autenticação: token do GitHub (fine-grained, só este repositório, "Contents: read and
write") na variável RASTRO_GITHUB_TOKEN. O token nunca aparece em logs ou mensagens.
"""

import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from rastro import site

log = logging.getLogger(__name__)

RAMO = "gh-pages"
PREFIXO_TAG = "site-"
MANTER = 5
AUTOR = ("Rastro Público (coleta)", "coleta@rastro-publico.invalid")


class ErroPublicacao(RuntimeError):
    pass


class Git:
    """Repositório temporário ligado ao remoto, com o token fora de qualquer saída."""

    def __init__(self, repo: str, token: str | None):
        self.token = token
        if token and repo.startswith("https://"):
            self.url = repo.replace("https://", f"https://x-access-token:{token}@", 1)
        else:
            self.url = repo  # caminho local (testes) ou URL já autenticada pelo ambiente
        self.dir = Path(tempfile.mkdtemp(prefix="rastro-site-"))
        self("init", "-q")
        self("config", "user.name", AUTOR[0])
        self("config", "user.email", AUTOR[1])
        self("remote", "add", "origin", self.url)

    def _limpar(self, texto: str) -> str:
        return texto.replace(self.token, "***") if self.token else texto

    def __call__(self, *args: str, verificar: bool = True) -> str:
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        r = subprocess.run(["git", *args], cwd=self.dir, capture_output=True, text=True, env=env)
        if verificar and r.returncode != 0:
            raise ErroPublicacao(
                self._limpar(f"git {' '.join(args)} falhou: {r.stderr.strip() or r.stdout}")
            )
        return r.stdout

    def tags_remotas(self) -> list[tuple[str, str]]:
        """[(tag, sha)] das publicações, da mais recente para a mais antiga."""
        saida = self("ls-remote", "--tags", "origin", f"refs/tags/{PREFIXO_TAG}*")
        tags = []
        for linha in saida.splitlines():
            sha, ref = linha.split("\t")
            if not ref.endswith("^{}"):
                tags.append((ref.removeprefix("refs/tags/"), sha))
        return sorted(tags, reverse=True)

    def sha_do_ramo(self) -> str | None:
        saida = self("ls-remote", "--heads", "origin", RAMO).strip()
        return saida.split("\t")[0] if saida else None

    def fechar(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


def _manifesto_publicado(git: Git) -> dict | None:
    if not git.sha_do_ramo():
        return None
    git("fetch", "-q", "--depth=1", "origin", RAMO)
    conteudo = git("show", "FETCH_HEAD:dados/manifesto.json", verificar=False)
    try:
        return json.loads(conteudo) if conteudo else None
    except ValueError:
        return None


def publicar(
    dist: Path,
    repo: str,
    token: str | None = None,
    manter: int = MANTER,
    agora: datetime | None = None,
    simular: bool = False,
) -> str:
    """Publica `dist` (frontend compilado + `dados/`) no gh-pages. Devolve a tag criada.

    Tudo ou nada: se a verificação falhar, nada é enviado e o site continua como está.
    Com `simular`, faz a mesma verificação contra o site publicado e para antes de enviar:
    devolve a tag que seria criada.
    """
    agora = agora or datetime.now(UTC)
    tag = f"{PREFIXO_TAG}{agora:%Y%m%d-%H%M%S}"
    git = Git(repo, token)
    try:
        anterior = _manifesto_publicado(git)
        problemas = site.verificar(dist / "dados", anterior)
        if problemas:
            raise ErroPublicacao("publicação cancelada:\n- " + "\n- ".join(problemas))
        if simular:
            log.info("Simulação: verificação ok; nada foi enviado (seria %s)", tag)
            return tag

        git("checkout", "-q", "--orphan", RAMO)
        shutil.copytree(dist, git.dir, dirs_exist_ok=True)
        (git.dir / ".nojekyll").write_text("")  # o Pages serve os arquivos como estão
        manifesto = json.loads((dist / "dados" / "manifesto.json").read_text())
        git("add", "-A")
        met = manifesto["metodologia"]
        mensagem = (
            f"Publicação {tag}\n\nColeta: {manifesto.get('ultima_coleta')}\n"
            f"Código: {manifesto.get('codigo')}\n"
            f"Metodologia: {met['versao']} ({met['hash']})"
        )
        git("commit", "-q", "-m", mensagem)
        git("tag", tag)
        git("push", "-q", "--force", "origin", f"HEAD:refs/heads/{RAMO}")
        git("push", "-q", "origin", f"refs/tags/{tag}")

        antigas = [t for t, _ in git.tags_remotas()][manter:]
        if antigas:
            git("push", "-q", "origin", "--delete", *[f"refs/tags/{t}" for t in antigas])
        log.info("Publicado %s (%d snapshots antigos removidos)", tag, len(antigas))
        return tag
    finally:
        git.fechar()


def baixar_publicado(repo: str, destino: Path, token: str | None = None) -> dict | None:
    """Copia o `dados/` da publicação no ar para `destino` e devolve o manifesto dela.

    É o ponto de partida da exportação incremental: com o `indice.json` anterior na pasta,
    `rastro exportar-site` reaproveita os grupos sem mudança. Sem publicação (ou sem
    `dados/` nela), devolve None e deixa `destino` vazio: a exportação será completa.
    """
    destino.mkdir(parents=True, exist_ok=True)
    if any(destino.iterdir()):
        raise ErroPublicacao(f"{destino} não está vazia")
    git = Git(repo, token)
    try:
        if not git.sha_do_ramo():
            return None
        git("fetch", "-q", "--depth=1", "origin", RAMO)
        if not git("ls-tree", "-d", "FETCH_HEAD", "dados").strip():
            return None
        pacote = git.dir / "dados.tar"
        git("archive", "--format=tar", "-o", str(pacote), "FETCH_HEAD", "dados")
        with tarfile.open(pacote) as tar:
            membros = []
            for m in tar.getmembers():
                nome = m.name.removeprefix("dados/")
                if nome in ("", "dados"):
                    continue
                m.name = nome
                membros.append(m)
            # filtro "data": recusa caminhos absolutos, "..", links e arquivos especiais
            tar.extractall(destino, members=membros, filter="data")
        manifesto = destino / "manifesto.json"
        return json.loads(manifesto.read_text()) if manifesto.exists() else None
    finally:
        git.fechar()


def listar(repo: str, token: str | None = None) -> list[dict]:
    git = Git(repo, token)
    try:
        atual = git.sha_do_ramo()
        return [{"tag": t, "sha": s, "no_ar": s == atual} for t, s in git.tags_remotas()]
    finally:
        git.fechar()


def reverter(repo: str, token: str | None = None, para: str | None = None) -> str:
    """Volta o site para a publicação `para` (padrão: a anterior à que está no ar)."""
    git = Git(repo, token)
    try:
        tags = git.tags_remotas()
        if not tags:
            raise ErroPublicacao("nenhuma publicação anterior encontrada")
        if para is None:
            atual = git.sha_do_ramo()
            indices = [i for i, (_, s) in enumerate(tags) if s == atual]
            if not indices or indices[0] + 1 >= len(tags):
                raise ErroPublicacao("não há publicação anterior à que está no ar")
            para = tags[indices[0] + 1][0]
        elif para not in {t for t, _ in tags}:
            raise ErroPublicacao(f"tag {para} não existe (use `rastro listar-publicacoes`)")
        git("fetch", "-q", "--depth=1", "origin", f"refs/tags/{para}:refs/tags/{para}")
        git("push", "-q", "--force", "origin", f"refs/tags/{para}^{{commit}}:refs/heads/{RAMO}")
        log.info("Site revertido para %s", para)
        return para
    finally:
        git.fechar()
