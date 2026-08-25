from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://movieclub:movieclub@localhost:5433/movieclub"
    secret_key: str = "dev-secret-change-me"
    omdb_api_key: str = ""
    omdb_base_url: str = "https://www.omdbapi.com/"

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value.removeprefix("postgresql://")
        elif value.startswith("postgres://"):
            value = "postgresql+psycopg://" + value.removeprefix("postgres://")
        is_remote = "localhost" not in value and "127.0.0.1" not in value
        if value.startswith("postgresql+psycopg://") and "sslmode=" not in value and is_remote:
            separator = "&" if "?" in value else "?"
            value += f"{separator}sslmode=require"
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
