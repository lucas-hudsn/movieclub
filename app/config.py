from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://movieclub:movieclub@localhost:5433/movieclub"
    secret_key: str = "dev-secret-change-me"
    omdb_api_key: str = ""
    omdb_base_url: str = "https://www.omdbapi.com/"


@lru_cache
def get_settings() -> Settings:
    return Settings()
