from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import default_database_path, settings_env_path


class Settings(BaseSettings):
    app_name: str = "Streaming Finder API"
    app_version: str = "0.16.0"
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    tmdb_read_access_token: SecretStr | None = None
    database_path: str = str(default_database_path())

    # The actual env-file path is supplied by get_settings() so a packaged
    # executable can keep secrets in the user's writable AppData directory.
    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings(
        _env_file=settings_env_path(),
        _env_file_encoding="utf-8",
    )
