from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Streaming Finder API"
    app_version: str = "0.7.0"
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    tmdb_read_access_token: SecretStr | None = None
    database_path: str = "data/streaming_finder.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
