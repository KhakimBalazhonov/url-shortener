from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, FutureDatetime, HttpUrl, field_validator


class LinkCreateRequest(BaseModel):
    original_url: Annotated[HttpUrl, Field(min_length=6, max_length=2048)]
    short_code: Annotated[str | None, Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")] = None
    expires_at: FutureDatetime | None = None

    @field_validator("expires_at")
    @classmethod
    def must_have_tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("expires_at must include timezone")
        return v


class LinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    short_url: str
    expires_at: datetime | None = None
