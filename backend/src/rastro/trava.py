"""Uma coleta por vez: trava no próprio banco (advisory lock do PostgreSQL).

Duas coletas ao mesmo tempo gravariam no mesmo banco e disputariam a publicação no
gh-pages (uma poderia publicar por cima da outra). `rastro coleta-exclusiva <comando>`
pega a trava e roda o comando; se outra coleta já estiver com ela, sai sem fazer nada,
com aviso.

A trava pertence a uma conexão aberta durante toda a coleta, que faz uma consulta leve a
cada minuto. Se o processo morrer (fim do tempo do agendador, Republish, reinício), a
conexão cai e o PostgreSQL solta a trava sozinho.

Coleta anterior interrompida: se a conexão dela continuar aberta no banco sem dar sinal
(nenhuma consulta há mais de `LIMITE_PARADA`) ou passar de `LIMITE_DURACAO` (o Replit
encerra execuções agendadas em 11 h), ela é tratada como interrompida: a conexão é
encerrada no banco, a trava se solta e esta execução começa a coleta de novo. Assim a
coleta nunca fica bloqueada para sempre.

Ao pegar a trava, as linhas da tabela `coleta` ainda "executando" (de uma execução que
morreu sem registrar o fim) passam a "interrompida": com a trava na mão, nenhuma outra
coleta pode estar rodando.
"""

import logging
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta

from sqlalchemy import Connection, Engine, create_engine, text

log = logging.getLogger(__name__)

# número fixo da trava da coleta (qualquer inteiro de 64 bits, igual em todo o projeto)
CHAVE = 7_270_001
NOME_CONEXAO = "rastro-coleta"
INTERVALO_PING = 60.0
# sem nenhuma consulta por 10 pings seguidos: o processo dono da trava não está mais vivo
LIMITE_PARADA = timedelta(minutes=10)
# acima do limite de 11 h do Replit para execuções agendadas
LIMITE_DURACAO = timedelta(hours=12)
ERRO_INTERROMPIDA = (
    "interrompida: a execução terminou sem registrar o fim (processo encerrado, "
    "Republish ou limite de tempo do agendador)"
)


class ColetaEmAndamento(RuntimeError):
    def __init__(self, desde: datetime | None, detalhe: str = ""):
        self.desde = desde
        quando = f" desde {desde:%d/%m/%Y %H:%M:%S %Z}" if desde else ""
        super().__init__(f"outra coleta está em andamento{quando}{detalhe}")


def engine_direto(engine: Engine) -> Engine:
    """Engine sem o pooler do Neon (host "-pooler"), se for o caso.

    Num pooler por transação, a trava ficaria presa a uma conexão do pooler, e não à da
    coleta. O endereço direto do Neon é o mesmo host sem "-pooler".
    """
    host = engine.url.host or ""
    if "-pooler." not in host:
        return engine
    return create_engine(engine.url.set(host=host.replace("-pooler.", ".", 1)))


def _dono(con: Connection) -> dict | None:
    """Conexão que segura a trava: pid, início e há quanto tempo está parada."""
    linha = con.execute(
        text(
            "SELECT a.pid, a.backend_start, a.state, "
            "now() - a.state_change AS parada, now() - a.backend_start AS idade "
            "FROM pg_locks l JOIN pg_stat_activity a USING (pid) "
            "WHERE l.locktype = 'advisory' AND l.granted AND l.objid = :chave"
        ),
        {"chave": CHAVE},
    ).first()
    return dict(linha._mapping) if linha else None


def _interrompida(dono: dict, limite_parada: timedelta, limite_duracao: timedelta) -> str | None:
    """Motivo para tratar a coleta dona da trava como interrompida, ou None se viva."""
    if dono["idade"] is not None and dono["idade"] > limite_duracao:
        return f"aberta há {dono['idade']}, acima do limite de {limite_duracao}"
    if dono["state"] != "active" and dono["parada"] is not None and dono["parada"] > limite_parada:
        return f"sem nenhuma consulta há {dono['parada']}"
    return None


def _pegar(con: Connection) -> bool:
    return bool(con.scalar(text("SELECT pg_try_advisory_lock(:chave)"), {"chave": CHAVE}))


def _liberar_interrompida(
    con: Connection, limite_parada: timedelta, limite_duracao: timedelta
) -> bool:
    """Se a dona da trava estiver interrompida, encerra a conexão dela e pega a trava."""
    dono = _dono(con)
    if dono is None:  # soltou entre as duas consultas
        return _pegar(con)
    motivo = _interrompida(dono, limite_parada, limite_duracao)
    if motivo is None:
        raise ColetaEmAndamento(dono["backend_start"])
    log.warning(
        "Trava da coleta: a coleta anterior (desde %s) foi interrompida (%s); "
        "encerrando a conexão dela e retomando",
        f"{dono['backend_start']:%d/%m/%Y %H:%M:%S %Z}", motivo,
    )  # fmt: skip
    if not con.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": dono["pid"]}):
        raise ColetaEmAndamento(
            dono["backend_start"], f" ({motivo}), mas o banco não deixou encerrar a conexão dela"
        )
    # o encerramento é assíncrono: espera a trava se soltar
    for _ in range(20):
        if _pegar(con):
            print(
                "AVISO: a coleta anterior foi interrompida sem soltar a trava "
                f"({motivo}). A trava foi liberada e a coleta recomeça agora.",
                flush=True,
            )
            return True
        time.sleep(0.5)
    raise ColetaEmAndamento(dono["backend_start"], " (a conexão dela não fechou a tempo)")


def marcar_interrompidas(con: Connection) -> int:
    """Linhas "executando" de execuções que morreram passam a "interrompida"."""
    if con.scalar(text("SELECT to_regclass('coleta')")) is None:  # banco ainda sem migrações
        return 0
    n = con.execute(
        text(
            "UPDATE coleta SET status = 'interrompida', finalizada_em = now(), "
            "erro = :erro || coalesce(E'\\n' || erro, '') WHERE status = 'executando'"
        ),
        {"erro": ERRO_INTERROMPIDA},
    ).rowcount
    if n:
        log.warning("Trava da coleta: %d registro(s) de coleta interrompida marcados", n)
    return n


@contextmanager
def trava_coleta(
    engine: Engine,
    intervalo_ping: float = INTERVALO_PING,
    limite_parada: timedelta = LIMITE_PARADA,
    limite_duracao: timedelta = LIMITE_DURACAO,
):
    """Segura a trava da coleta enquanto o bloco roda; ColetaEmAndamento se ocupada.

    Uma coleta anterior interrompida que ainda segura a trava é encerrada (ver o módulo).
    """
    con = engine.connect()
    try:
        con.execute(text("SELECT set_config('application_name', :n, false)"), {"n": NOME_CONEXAO})
        if not _pegar(con):
            _liberar_interrompida(con, limite_parada, limite_duracao)
        marcar_interrompidas(con)
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
            try:
                con.execute(text("SELECT pg_advisory_unlock(:chave)"), {"chave": CHAVE})
                con.commit()
            except Exception as exc:  # conexão encerrada (ex.: tomada por outra execução)
                log.warning("Trava da coleta: já estava solta ao terminar (%s)", exc)
    finally:
        con.close()


def executar_exclusivo(engine: Engine, comando: list[str]) -> int:
    """Roda `comando` com a trava. Devolve o código dele, ou 0 (com aviso) se ocupada."""
    try:
        with trava_coleta(engine_direto(engine)):
            log.info("Trava da coleta obtida; executando: %s", " ".join(comando))
            return subprocess.run(comando, check=False).returncode
    except ColetaEmAndamento as exc:
        print(
            f"AVISO: {exc}. Esta execução não fez nada; a coleta em andamento continua. "
            "Se ela tiver travado, pare-a no painel do Replit e rode de novo.",
            flush=True,
        )
        return 0
