import os
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
    # origens que podem chamar a API de auditoria (site no GitHub Pages + dev local),
    # separadas por vírgula
    cors_origens: str = "https://fasn98.github.io,http://localhost:5173"
    user_agent: str = "rastro-publico/0.1 (+https://github.com/fasn98/rastro-publico)"
    # Travas de publicação do módulo de políticos (valem para a API e para o site exportado).
    # O padrão é a decisão vigente; uma variável RASTRO_POL_PUBLICAR_* pode sobrepor.
    pol_publicar_tse: bool = True  # eleitos 2024 e 2022 (aprovado em 06/10/2026)
    pol_publicar_tse_2026: bool = False  # eleitos 2026: aguardando o fim do 2º turno
    pol_publicar_emendas: bool = False  # aguardando validação do cruzamento de autores

    @property
    def origens_cors(self) -> list[str]:
        return [o.strip() for o in self.cors_origens.split(",") if o.strip()]


def _url_do_ambiente() -> str | None:
    """Usa o DATABASE_URL do Replit (ou de outro provedor) se RASTRO_DATABASE_URL não existir.

    Esses provedores entregam `postgresql://...`; o SQLAlchemy precisa do driver explícito.
    """
    if os.environ.get("RASTRO_DATABASE_URL") or not os.environ.get("DATABASE_URL"):
        return None
    url = os.environ["DATABASE_URL"]
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo) :]
    return url


@lru_cache
def get_settings() -> Settings:
    url = _url_do_ambiente()
    return Settings(database_url=url) if url else Settings()
