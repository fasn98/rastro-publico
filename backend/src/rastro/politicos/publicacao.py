"""Travas de publicação: dados novos só aparecem nas telas depois de validados.

Os dados podem ser coletados e conferidos antes (pela API de auditoria e pelo banco), mas
a API pública (e o site estático, que é gerado a partir dela) só os mostra quando a trava
estiver ligada. As travas ficam em `rastro.config.Settings` (padrão = decisão vigente,
variáveis RASTRO_POL_PUBLICAR_TSE, RASTRO_POL_PUBLICAR_TSE_2026,
RASTRO_POL_PUBLICAR_EMENDAS e RASTRO_POL_PUBLICAR_GESTOES sobrepõem).
"""

from rastro.config import get_settings

# eleições cujos eleitos ainda não exercem o mandato (publicação separada)
ELEICOES_FUTURAS = (2026,)


def tse() -> bool:
    return get_settings().pol_publicar_tse


def tse_2026() -> bool:
    return get_settings().pol_publicar_tse_2026


def emendas() -> bool:
    return get_settings().pol_publicar_emendas


def gestoes() -> bool:
    """Prefeitos eleitos por exercício (ADR-0018)."""
    return get_settings().pol_publicar_gestoes
