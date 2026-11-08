from functools import lru_cache
from typing import Literal

from pydantic import HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "URL Shortener"
    DEBUG: bool = False
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    ENVIRONMENT: Literal["local", "test", "production"] = "local"

    SQIDS_ALPHABET: SecretStr  # Алфавит для генерации коротких кодов

    BASE_URL: HttpUrl

    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_USER: str
    POSTGRES_PASSWORD: SecretStr
    POSTGRES_DB_NAME: str

    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PASSWORD: SecretStr

    CACHE_TTL_SECONDS: int = 3600  # Максимальное время хранения ссылки в кеше
    CACHE_MISS_TTL_SECONDS: int = 60  # TTL для кеширования отсутствующих коротких кодов

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD.get_secret_value()}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB_NAME}"
        )

    @property
    def celery_broker_url(self) -> str:
        return f"redis://default:{self.REDIS_PASSWORD.get_secret_value()}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def cache_url(self) -> str:
        return f"redis://default:{self.REDIS_PASSWORD.get_secret_value()}@{self.REDIS_HOST}:{self.REDIS_PORT}/1"

    @property
    def is_prod(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue] # поля читаются из .env
