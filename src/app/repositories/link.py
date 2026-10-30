from datetime import datetime
from typing import cast

from sqlalchemy import CursorResult, delete, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Link


class LinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_and_count(self, code: str) -> str | None:
        stmt = (
            update(Link)
            .where(
                Link.short_code == code,
                or_(Link.expires_at.is_(None), Link.expires_at > func.now()),
            )
            .values(clicks_count=Link.clicks_count + 1)
            .returning(Link.original_url)
        )

        return await self._session.scalar(stmt)

    async def create(
        self, *, original_url: str, short_code: str, expires_at: datetime | None
    ) -> Link:
        link = Link(original_url=original_url, short_code=short_code, expires_at=expires_at)
        self._session.add(link)
        return link

    async def delete_expired(self) -> int:
        stmt = delete(Link).where(Link.expires_at < func.now())
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount
