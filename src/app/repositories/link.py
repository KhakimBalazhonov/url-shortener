from typing import cast

from sqlalchemy import ColumnElement, CursorResult, delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Link


def _is_active() -> ColumnElement[bool]:
    """Ссылка бессрочная или ее срок еще не вышел (по времени в БД)."""
    return or_(Link.expires_at.is_(None), Link.expires_at > func.now())


class LinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_next_sequence_id(self) -> int:
        """Получает следующий ID из кешированной последовательности PostgreSQL."""
        stmt = text("SELECT nextval('link_id_seq')")
        return await self._session.scalar(stmt)

    async def resolve_and_count(self, short_code: str) -> str | None:
        stmt = (
            update(Link)
            .where(Link.short_code == short_code, _is_active())
            .values(clicks_count=Link.clicks_count + 1)
            .returning(Link.original_url)
        )

        return await self._session.scalar(stmt)

    async def create(self, link: Link) -> None:
        self._session.add(link)

    async def delete_expired(self) -> int:
        stmt = delete(Link).where(Link.expires_at < func.now())
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount

    async def get_by_short_code(self, short_code: str) -> Link | None:
        stmt = select(Link).where(Link.short_code == short_code, _is_active())
        result = await self._session.scalar(stmt)
        return result
