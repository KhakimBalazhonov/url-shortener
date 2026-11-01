from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, FutureDatetime, HttpUrl, field_validator

RESERVED_SLUGS = frozenset({"docs", "redoc", "shorten", "api", "health", "metrics"})


class LinkCreateRequest(BaseModel):
    original_url: Annotated[HttpUrl, Field(min_length=6, max_length=2048)]
    short_code: Annotated[str | None, Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")] = None
    expires_at: FutureDatetime | None = None

    @field_validator("expires_at")
    @classmethod
    def must_have_tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("Поле expires_at должно содержать часовой пояс")
        return v

    @field_validator("short_code")
    @classmethod
    def not_reserved(cls, v: str | None) -> str | None:
        if v is not None and v.lower() in RESERVED_SLUGS:
            raise ValueError("Этот код зарезервирован и недоступен для использования")
        return v


class LinkResponse(BaseModel):
    short_url: str
    expires_at: datetime | None = None


class LinkStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    original_url: str
    short_code: str
    clicks_count: int
    created_at: datetime
    expires_at: datetime | None
