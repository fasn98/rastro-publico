from rastro.coletores import ibge, siconfi
from rastro.coletores.base import Coletor

COLETORES: dict[str, Coletor] = {
    "ibge-municipios": ibge.coletar,
    "ibge-populacao": ibge.coletar_populacao,
    "siconfi-entes": siconfi.coletar,
}
