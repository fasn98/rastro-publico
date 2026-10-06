from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RASTRO_", extra="ignore")

    database_url: str = "postgresql+psycopg://rastro:rastro@localhost:5432/rastro"
    http_timeout: float = 60.0
    http_tentativas: int = 4
    # limite de requisições por segundo a cada API (0 = sem limite)
    req_por_segundo: float = 1.0
    # itens por página nas APIs ORDS do Tesouro (máximo aceito pela API: 5000)
    siconfi_itens_por_pagina: int = 5000
    # guarda toda resposta HTTP (payload, URL, data, SHA-256) para auditoria
    arquivar_respostas: bool = True
    user_agent: str = "rastro-publico/0.1 (+https://github.com/fasn98/rastro-publico)"
    # Travas de publicação do módulo de políticos (valem para a API e para o site exportado).
    # O padrão é a decisão vigente; uma variável RASTRO_POL_PUBLICAR_* pode sobrepor.
    pol_publicar_tse: bool = True  # eleitos 2024 e 2022 (aprovado em 06/10/2026)
    pol_publicar_tse_2026: bool = False  # eleitos 2026: aguardando o fim do 2º turno
    pol_publicar_emendas: bool = False  # aguardando validação do cruzamento de autores


@lru_cache
def get_settings() -> Settings:
    return Settings()
