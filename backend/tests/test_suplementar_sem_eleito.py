"""Suplementar realizada e ainda sem eleito no arquivo do TSE: o motivo da pendência diz só o
que o arquivo mostra.

A fixture tse_consulta_cand_2024_SP_narandiba.csv traz as 6 linhas de prefeito de Narandiba/SP
(código TSE 67458) no consulta_cand_2024_SP.csv do TSE (consulta_cand_2024.zip, Last-Modified
28/10/2026 05:25:20 GMT, linhas geradas em 28/10/2026), já SEM as colunas pessoais. A eleição
suplementar de 25/10/2026 (eleição 6284) não traz eleito no arquivo.
"""

import csv
import io

from conftest import FIXTURES
from rastro.politicos import tse

POL = FIXTURES / "politicos"


def _linhas() -> list[dict]:
    texto = (POL / "tse_consulta_cand_2024_SP_narandiba.csv").read_text()
    return list(csv.DictReader(io.StringIO(texto), delimiter=";"))


def test_suplementar_realizada_sem_eleito_fica_pendente_com_motivo_do_arquivo():
    ((ue, cargo, eleitos, posteriores, segundo_turno),) = tse.selecionar_eleitos(
        _linhas(), {"PREFEITO": "prefeito"}
    )
    assert (ue, cargo, eleitos, segundo_turno) == ("67458", "PREFEITO", [], [])
    assert [p[0]["CD_ELEICAO"] for p in posteriores] == ["6284"]
    assert tse._motivo(cargo, posteriores) == (
        "Não consta prefeito eleito no arquivo do TSE. Suplementar de Narandiba - out/26, "
        "realizada em 25/10/2026: o arquivo do TSE (versão de 28/10/2026) não traz eleito."
    )


def test_suplementar_ainda_por_vir_mantem_o_texto_de_marcada():
    """Mesmas linhas, com a data do arquivo anterior à da eleição (como no arquivo de 09/10)."""
    linhas = [{**r, "DT_GERACAO": "09/10/2026"} for r in _linhas()]
    ((_, cargo, _, posteriores, _),) = tse.selecionar_eleitos(linhas, {"PREFEITO": "prefeito"})
    assert tse._motivo(cargo, posteriores) == (
        "Não consta prefeito eleito no arquivo do TSE. Suplementar de Narandiba - out/26 "
        "marcada para 25/10/2026, ainda sem resultado no arquivo."
    )
