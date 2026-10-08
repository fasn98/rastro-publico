"""Uma coleta por vez: trava no próprio banco (advisory lock do PostgreSQL).

Duas coletas ao mesmo tempo gravariam no mesmo banco e disputariam a publicação no
gh-pages (uma poderia publicar por cima da outra). `rastro coleta-exclusiva <comando>`
pega a trava e roda o comando; se outra coleta já estiver com ela, sai sem fazer nada,
com aviso.

A trava pertence a uma conexão aberta durante toda a coleta. Se o processo morrer (fim
do tempo do agendador, reinício), a conexão cai e o PostgreSQL solta a trava sozinho: não
fica trava esquecida. Uma consulta leve a cada minuto mantém a conexão ativa.
"""

import logging
import subprocess
import threading
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import Engine, text

log = logging.getLogger(__name__)

# número fixo da trava da coleta (qualquer inteiro de 64 bits, igual em todo o projeto)
CHAVE = 7_270_001
NOME_CONEXAO = "rastro-coleta"
INTERVALO_PING = 60.0


class ColetaEmAndamento(RuntimeError):
    def __init__(self, desde: datetime | None):
        self.desde = desde
        quando = f" desde {desde:%d/%m/%Y %H:%M:%S %Z}" if desde else ""
        super().__init__(f"outra coleta está em andamento{quando}")


def _quem_tem(engine: Engine) -> datetime | None:
    """Início da conexão que segura a trava (para a mensagem)."""
    with engine.connect() as con:
        return con.scalar(
            text(
                "SELECT a.backend_start FROM pg_locks l JOIN pg_stat_activity a USING (pid) "
                "WHERE l.locktype = 'advisory' AND l.granted AND l.objid = :chave"
            ),
            {"chave": CHAVE},
        )


@contextmanager
def trava_coleta(engine: Engine, intervalo_ping: float = INTERVALO_PING):
    """Segura a trava da coleta enquanto o bloco roda; ColetaEmAndamento se ocupada."""
    con = engine.connect()
    try:
        con.execute(text("SELECT set_config('application_name', :n, false)"), {"n": NOME_CONEXAO})
        if not con.scalar(text("SELECT pg_try_advisory_lock(:chave)"), {"chave": CHAVE}):
            raise ColetaEmAndamento(_quem_tem(engine))
        con.commit()
        parar = threading.Event()

        def manter_viva():
            while not parar.wait(intervalo_ping):
                try:
                    con.execute(text("SELECT 1"))
                    con.commit()
                except Exception as exc:  # conexão caiu: a trava se perdeu com ela
                    log.warning("Trava da coleta: conexão perdida (%s)", exc)
                    return

        ping = threading.Thread(target=manter_viva, daemon=True)
        ping.start()
        try:
            yield
        finally:
            parar.set()
            ping.join(timeout=5)
            con.execute(text("SELECT pg_advisory_unlock(:chave)"), {"chave": CHAVE})
            con.commit()
    finally:
        con.close()


def executar_exclusivo(engine: Engine, comando: list[str]) -> int:
    """Roda `comando` com a trava. Devolve o código dele, ou 0 (com aviso) se ocupada."""
    try:
        with trava_coleta(engine):
            log.info("Trava da coleta obtida; executando: %s", " ".join(comando))
            return subprocess.run(comando, check=False).returncode
    except ColetaEmAndamento as exc:
        print(
            f"AVISO: {exc}. Esta execução não fez nada; a coleta em andamento continua. "
            "Se ela tiver travado, pare-a no painel do Replit e rode de novo.",
            flush=True,
        )
        return 0
