from functools import lru_cache
from pathlib import Path
from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class _Settings(BaseSettings):
    BC_STORE_HASH: str
    BC_ACCESS_TOKEN: str
    BC_CHANNEL_ID: int = 1
    BC_ENV: str = "production"

    VERTEX_API_KEY: str
    VERTEX_MODEL_ID: str
    DEBUG_MODE: bool = False
    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parent.parent

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        extra="ignore",
        env_file_encoding="utf-8",
    )


@lru_cache
def _cached() -> "_Settings":
    return _Settings()


settings = _cached()

BC_ENV = settings.BC_ENV
DEBUG_MODE = settings.DEBUG_MODE
BC_CHANNEL_ID = settings.BC_CHANNEL_ID
BC_STORE_HASH = settings.BC_STORE_HASH
BC_ACCESS_TOKEN = settings.BC_ACCESS_TOKEN
VERTEX_API_KEY = settings.VERTEX_API_KEY
VERTEX_MODEL_ID = settings.VERTEX_MODEL_ID
