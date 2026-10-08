"""Uma coleta por vez: a segunda sai sem fazer nada, e a trava se solta sozinha."""

import pytest

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
