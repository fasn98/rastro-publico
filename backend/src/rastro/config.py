from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RASTRO_", extra="ignore")

    database_url: str = "postgresql+psycopg://rastro:rastro@localhost:5432/rastro"
    http_timeout: float = 60.0
    http_tentativas: int = 4
    # pausa entre requisições aos endpoints pesados do SICONFI (segundos)
    siconfi_intervalo: float = 0.2
    user_agent: str = "rastro-publico/0.1 (+https://github.com/fasn98/rastro-publico)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
