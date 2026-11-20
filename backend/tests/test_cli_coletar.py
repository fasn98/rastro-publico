"""`rastro coletar` (cadastros da coleta agendada: ibge-municipios, ibge-populacao,
siconfi-entes).

De 09/10/2026 (ff85778d) a 20/11/2026, um `import` local de `novo_cliente` dentro de
`main()`, no ramo do `portao`, tornava o nome local à função inteira: no ramo do
`coletar`, a chamada caía em `UnboundLocalError` antes de qualquer coleta, e o
`coleta_sp.sh` seguia com "AVISO: cadastros com falha" (log da Coleta #2 do Actions,
20/11/2026). Resposta real gravada: `ibge_municipios.json` (API de localidades do IBGE).
"""

import respx
from sqlalchemy import func, select

from conftest import FIXTURES, URL_TESTE
from rastro import cli
from rastro.coletores import ibge
from rastro.config import get_settings
from rastro.db import get_engine, get_sessionmaker
from rastro.models import Coleta, Municipio


def _limpar_caches():
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


def test_coletar_ibge_municipios_pela_cli(session, engine, monkeypatch):
    # a CLI usa o banco das configurações: aqui, o banco de teste
    monkeypatch.setenv("RASTRO_DATABASE_URL", URL_TESTE)
    _limpar_caches()
    try:
        with respx.mock:
            respx.get(ibge.URL_MUNICIPIOS).respond(
                content=(FIXTURES / "ibge_municipios.json").read_bytes(),
                headers={"content-type": "application/json"},
            )
            assert cli.main(["coletar", "ibge-municipios"]) == 0
    finally:
        get_engine().dispose()
        _limpar_caches()
    assert session.scalar(select(func.count()).select_from(Municipio)) == 3
    status = session.scalars(select(Coleta.status).where(Coleta.fonte == "ibge-municipios"))
    assert status.all() == ["sucesso"]
