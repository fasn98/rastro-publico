"""scripts/replit.sh: o Secret RASTRO_PAPEL sem diferenciar maiúsculas, e erro claro."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "replit.sh"


def _rodar(papel: str | None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "RASTRO_PAPEL"}
    if papel is not None:
        env["RASTRO_PAPEL"] = papel
    return subprocess.run(
        ["bash", str(SCRIPT), "--validar-papel"], env=env, capture_output=True, text=True
    )


@pytest.mark.parametrize(
    ("valor", "papel"),
    [
        ("auditoria", "auditoria"),
        ("AUDITORIA", "auditoria"),
        ("Auditoria ", "auditoria"),
        ("coleta", "coleta"),
        (" COLETA", "coleta"),
    ],
)
def test_papel_sem_diferenciar_maiusculas(valor, papel):
    r = _rodar(valor)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == papel


@pytest.mark.parametrize("valor", ["auditor", "coleta-sp", "api"])
def test_papel_invalido_lista_os_valores_aceitos(valor):
    r = _rodar(valor)
    assert r.returncode == 64
    assert f'RASTRO_PAPEL="{valor}" não é um papel válido' in r.stderr
    assert "Valores aceitos: coleta, auditoria" in r.stderr


@pytest.mark.parametrize("valor", [None, "", "   "])
def test_papel_ausente(valor):
    r = _rodar(valor)
    assert r.returncode == 64
    assert "RASTRO_PAPEL não está definido" in r.stderr
    assert "coleta, auditoria" in r.stderr
