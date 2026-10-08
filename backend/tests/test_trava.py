"""Uma coleta por vez: a segunda sai sem fazer nada, e a trava se solta sozinha."""

import pytest

import rastro.models  # noqa: F401  (cria a tabela coleta no banco de teste)
from rastro.trava import ColetaEmAndamento, executar_exclusivo, trava_coleta


def test_segunda_coleta_e_recusada_enquanto_a_primeira_roda(engine):
    with trava_coleta(engine):
        with pytest.raises(ColetaEmAndamento) as exc:
            with trava_coleta(engine):
                pass
        assert exc.value.desde is not None  # a mensagem diz desde quando
    # terminada a primeira, a próxima consegue
    with trava_coleta(engine):
        pass


def test_comando_roda_com_a_trava_e_devolve_o_codigo(engine, tmp_path):
    marca = tmp_path / "rodou"
    assert executar_exclusivo(engine, ["sh", "-c", f"touch {marca}"]) == 0
    assert marca.exists()
    assert executar_exclusivo(engine, ["sh", "-c", "exit 3"]) == 3


def test_coleta_em_andamento_sai_com_aviso_sem_rodar(engine, tmp_path, capsys):
    marca = tmp_path / "rodou"
    with trava_coleta(engine):
        codigo = executar_exclusivo(engine, ["sh", "-c", f"touch {marca}"])
    assert codigo == 0 and not marca.exists()
    assert "AVISO: outra coleta está em andamento desde" in capsys.readouterr().out


def test_trava_se_solta_quando_a_conexao_cai(engine):
    from sqlalchemy import text

    from rastro.trava import CHAVE

    con = engine.connect()
    assert con.scalar(text("SELECT pg_try_advisory_lock(:c)"), {"c": CHAVE})
    con.invalidate()  # processo morreu: a conexão fecha sem soltar a trava
    con.close()
    with trava_coleta(engine):
        pass


def test_coleta_anterior_interrompida_tem_a_trava_liberada_e_a_nova_retoma(engine, capsys):
    """Conexão esquecida aberta segurando a trava, sem consultas: é encerrada."""
    import time
    from datetime import timedelta

    from sqlalchemy import text

    from rastro.trava import CHAVE

    esquecida = engine.connect()
    assert esquecida.scalar(text("SELECT pg_try_advisory_lock(:c)"), {"c": CHAVE})
    esquecida.commit()
    time.sleep(1.2)
    with trava_coleta(engine, limite_parada=timedelta(seconds=1)):
        pass
    assert "A trava foi liberada e a coleta recomeça agora" in capsys.readouterr().out
    esquecida.invalidate()
    esquecida.close()


def test_coleta_viva_nao_tem_a_trava_tomada(engine):
    """Com a consulta periódica em dia, a coleta em andamento não é considerada parada."""
    import time
    from datetime import timedelta

    with trava_coleta(engine, intervalo_ping=0.2):
        time.sleep(1.5)
        with pytest.raises(ColetaEmAndamento):
            with trava_coleta(engine, limite_parada=timedelta(seconds=1)):
                pass


def test_coleta_acima_do_limite_de_duracao_e_interrompida(engine):
    from datetime import timedelta

    # a antiga perde a trava e termina sem erro; a nova roda
    with trava_coleta(engine, intervalo_ping=0.2):
        with trava_coleta(engine, limite_duracao=timedelta(0)):
            pass
    with trava_coleta(engine):
        pass


def test_registros_executando_viram_interrompida(engine, session):
    from rastro.models import Coleta

    session.add_all([Coleta(fonte="pol-camara", status="executando"),
                     Coleta(fonte="pol-senado", status="sucesso")])  # fmt: skip
    session.commit()
    with trava_coleta(engine):
        pass
    session.expire_all()
    por_fonte = {c.fonte: c for c in session.query(Coleta)}
    assert por_fonte["pol-camara"].status == "interrompida"
    assert por_fonte["pol-camara"].finalizada_em is not None
    assert por_fonte["pol-camara"].erro.startswith("interrompida:")
    assert por_fonte["pol-senado"].status == "sucesso"


def test_engine_direto_tira_o_pooler_do_neon():
    from sqlalchemy import create_engine

    from rastro.trava import engine_direto

    eng = create_engine("postgresql+psycopg://u:s@ep-abc-123-pooler.us-east-2.aws.neon.tech/db")
    assert engine_direto(eng).url.host == "ep-abc-123.us-east-2.aws.neon.tech"
    local = create_engine("postgresql+psycopg://u:s@localhost/db")
    assert engine_direto(local) is local
