import logging
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    LinkNotFoundError,
    SelfReferencingUrlError,
    ShortCodeAlreadyExistsError,
    ShortCodeGenerationError,
)
from app.models import Link
from app.repositories.link import LinkRepository
from app.schemas.link import LinkCreateRequest, LinkResponse, LinkStatsResponse
from app.services.keygen import encode_id

logger = logging.getLogger(__name__)

settings = get_settings()

MAX_ATTEMPTS = 5  # Sqids может сгенерировать уже занятый КАСТОМНЫЙ код,
# из-за чего клиент, который не задавал код получит 409

NOT_FOUND = "__NOT_FOUND__"


class LinkService:
    def __init__(self, session: AsyncSession, redis_client: Redis, repo: LinkRepository) -> None:
        self._session = session
        self._redis = redis_client
        self._repo = repo

    async def create_link(self, data: LinkCreateRequest) -> LinkResponse:
        is_custom_code = data.short_code is not None

        url = data.original_url
        base = settings.BASE_URL
        base_url = str(base).rstrip("/")  # Убирает лишние слэши

        # URL ведёт на сам сервис
        if url.host == base.host:
            logger.debug("Попытка создания петлевой ссылки %s", data.original_url)
            raise SelfReferencingUrlError()

        # Если клиент передал кастомный код, то попытка всего одна
        attempts = 1 if is_custom_code else MAX_ATTEMPTS

        for attempt in range(attempts):
            if is_custom_code:
                short_code = data.short_code
            else:
                sequence_id = await self._repo.get_next_sequence_id()
                short_code = encode_id(sequence_id)

            link = Link(
                original_url=str(data.original_url),
                short_code=short_code,
                expires_at=data.expires_at,
            )

            await self._repo.create(link)

            try:
                await self._session.commit()
                await self._redis.delete(f"link:{short_code}")  # Убирает метку «не найдено»
                logger.debug("Создана новая ссылка с кодом %s", short_code)
                return LinkResponse(short_url=f"{base_url}/{link.short_code}", expires_at=link.expires_at)
            except IntegrityError as e:
                await self._session.rollback()
                if getattr(e.orig, "sqlstate", None) == "23505":  # Нарушение уникальности
                    if is_custom_code:  # Если пользователь сам ввел занятый код — сразу 409
                        raise ShortCodeAlreadyExistsError from e
                    logger.info("Коллизия сгенерированного кода %s, попытка %d", short_code, attempt + 1)
                    # Если сгенерированный код совпал с существующим кастомным — след. попытка
                    continue
                raise

        raise ShortCodeGenerationError()

    async def get_target_url(self, short_code: str) -> str:
        logger.debug("Запрос на переход по короткой ссылке: %s", short_code)

        cached_url = await self._redis.get(f"link:{short_code}")

        if cached_url == NOT_FOUND:
            raise LinkNotFoundError(f"Ссылка с кодом {short_code} не найдена или срок ее действия истек")

        if isinstance(cached_url, str):
            logger.debug("Короткая ссылка %s найдена в кеше", short_code)
            await self._redis.incr(f"clicks:{short_code}")
            return cached_url

        logger.debug("Короткая ссылка %s отсутствует в кеше, выполняется запрос к БД", short_code)
        link = await self._repo.get_by_short_code(short_code)

        if link is None:
            logger.debug("Короткая ссылка %s не найдена в БД, в кеш записано %s", short_code, NOT_FOUND)
            await self._redis.set(f"link:{short_code}", NOT_FOUND, ex=settings.CACHE_MISS_TTL_SECONDS)
            raise LinkNotFoundError(f"Ссылка с кодом {short_code} не найдена или срок ее действия истек")

        ttl = settings.CACHE_TTL_SECONDS
        if link.expires_at is not None:
            remaining_seconds = int((link.expires_at - datetime.now(UTC)).total_seconds())
            if remaining_seconds <= 0:
                raise LinkNotFoundError(f"Ссылка с кодом {short_code} истекла")
            ttl = min(ttl, remaining_seconds)

        async with self._redis.pipeline(transaction=True) as pipe:
            logger.debug("Для ссылки с кодом %s задано значение в кеше c ttl: %s", short_code, ttl)
            pipe.set(f"link:{short_code}", link.original_url, ex=ttl)
            pipe.incr(f"clicks:{short_code}")
            await pipe.execute()

        return link.original_url

    async def get_stats(self, short_code: str) -> LinkStatsResponse:
        link = await self._repo.get_by_short_code(short_code)
        if link is None:
            raise LinkNotFoundError(f"Ссылка с кодом {short_code} не найдена или срок её действия истёк")
        stats = LinkStatsResponse.model_validate(link)
        pending = await self._redis.get(f"clicks:{short_code}")
        stats.clicks_count += int(pending or 0)
        return stats

    async def cleanup_expired_links(self) -> int:
        deleted_count = await self._repo.delete_expired()
        await self._session.commit()
        logger.info("Удалено истекших ссылок: %s", deleted_count)
        return deleted_count

    async def sync_clicks(self) -> int:
        """Обновляет счетчик кликов (из редис в бд)"""
        clicks_data: dict[str, int] = {}

        # scan_iter по умолчанию возвращает по 10 ключей за запрос
        # count=1000 позволяет перебирать большее количество ключей за раз
        async for key in self._redis.scan_iter("clicks:*", count=1000):
            short_code = key.removeprefix("clicks:")
            # getdel читает число и сразу удаляет ключ из Redis
            count = await self._redis.getdel(key)
            if count:
                clicks_data[short_code] = int(count)

        if not clicks_data:
            return 0

        try:
            await self._repo.increment_clicks_batch(clicks_data)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            for short_code, count in clicks_data.items():
                await self._redis.incrby(f"clicks:{short_code}", count)  # возвращаем клики обратно
            raise

        logger.info("Синхронизированы клики для %d ссылок", len(clicks_data))

        return len(clicks_data)
