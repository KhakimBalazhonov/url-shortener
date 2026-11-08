from typing import cast

from sqlalchemy import CursorResult, delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Link


class LinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_next_sequence_id(self) -> int:
        """
        Получает следующий ID из последовательности PostgreSQL.
        ID нужен, чтобы сгенерировать из него короткий код через Sqids.
        Отдельная последовательность используется вместо автоинкремента первичного ключа,
        чтобы получить ID до INSERT и сохранить запись сразу с готовым коротким кодом,
        без дополнительного UPDATE.
        """
        stmt = text("SELECT nextval('link_id_seq')")
        return await self._session.scalar(stmt)

    async def create(self, link: Link) -> None:
        """Добавляет новую ссылку в сессию базы данных"""
        self._session.add(link)

    async def delete_expired(self) -> int:
        """Удаляет из БД ссылки с истекшим сроком действия и возвращает количество удаленных ссылок"""
        stmt = delete(Link).where(Link.expires_at < func.now())
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount

    async def get_by_short_code(self, short_code: str) -> Link | None:
        """Возвращает ссылку по короткому коду"""
        stmt = select(Link).where(
            Link.short_code == short_code, or_(Link.expires_at.is_(None), Link.expires_at > func.now())
        )
        result = await self._session.scalar(stmt)
        return result

    async def increment_clicks_batch(self, clicks_data: dict[str, int]) -> None:
        """Сохраняет накопленные клики из Redis в БД"""
        for short_code, count in clicks_data.items():
            stmt = update(Link).where(Link.short_code == short_code).values(clicks_count=Link.clicks_count + count)
            await self._session.execute(stmt)
