"""Conferência da versão do código (o deployment do Replit não tem .git).

Sem rede: as "árvores" dos commits são montadas com o próprio `git` sobre uma pasta
temporária, e o hash tem de ser o mesmo que o Git calcula.
"""

import subprocess

from rastro import versao_codigo as vc


def _git(pasta, *args) -> str:
    return subprocess.run(
        ["git", "-C", str(pasta), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(pasta, sha: str) -> vc.Commit:
    """Árvore de `backend/` e `frontend/` do commit, como a API do GitHub devolve."""
    arquivos = {}
    for linha in _git(pasta, "ls-tree", "-r", sha).splitlines():
        meta, caminho = linha.split("\t")
        if caminho.startswith(vc.PASTAS):
            arquivos[caminho] = meta.split()[2]
    return vc.Commit(sha=sha, data="2026-10-09T00:00:00Z", arquivos=arquivos)


def test_hash_igual_ao_do_git(tmp_path):
    arq = tmp_path / "x.py"
    arq.write_bytes(b"print('rastro')\n")
    esperado = subprocess.run(
        ["git", "hash-object", str(arq)], check=True, capture_output=True, text=True
    ).stdout.strip()
    assert vc.blob_sha(arq.read_bytes()) == esperado


def _repo(tmp_path):
    """Três commits: v1, v2 (muda o backend) e v3 (só documentação)."""
    r = tmp_path / "repo"
    (r / "backend").mkdir(parents=True)
    _git(tmp_path, "init", "-q", str(r))
    _git(r, "config", "user.email", "teste@example.invalid")
    _git(r, "config", "user.name", "teste")
    shas = []
    for conteudo, doc in (("v1", "a"), ("v2", "a"), ("v2", "b")):
        (r / "backend" / "app.py").write_text(conteudo)
        (r / "README.md").write_text(doc)
        _git(r, "add", "-A")
        _git(r, "commit", "-q", "-m", conteudo + doc)
        shas.append(_git(r, "rev-parse", "HEAD"))
    commits = [_commit(r, s) for s in reversed(shas)]  # do main para trás
    return r, shas, commits


def test_em_dia_mesmo_com_commit_so_de_documentacao(tmp_path):
    r, shas, commits = _repo(tmp_path)
    res = vc.comparar(r, commits)
    assert res.publicado.sha == shas[2] and res.atras == 0
    assert vc.mensagem(res).startswith("Código publicado em dia")


def test_codigo_atrasado_avisa_com_os_dois_hashes(tmp_path):
    r, shas, commits = _repo(tmp_path)
    (r / "backend" / "app.py").write_text("v1")  # disco com o código do 1º commit
    res = vc.comparar(r, commits)
    assert res.publicado.sha == shas[0] and res.atras == 1
    texto = vc.mensagem(res)
    assert texto.startswith("AVISO") and shas[0][:7] in texto and shas[2][:7] in texto


def test_codigo_que_nao_bate_com_nenhum_commit(tmp_path):
    r, _, commits = _repo(tmp_path)
    (r / "backend" / "app.py").write_text("alterado no servidor")
    res = vc.comparar(r, commits)
    assert res.publicado is None and res.diferentes == 1
    assert "não corresponde" in vc.mensagem(res)


def test_falha_na_conferencia_nao_derruba_a_coleta(tmp_path):
    avisos = []

    def sem_rede():
        raise OSError("sem rede")

    assert vc.conferir(tmp_path, sem_rede, avisos.append) is None
    assert avisos[0].startswith("AVISO: não foi possível conferir")
