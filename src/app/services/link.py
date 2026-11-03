import logging

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


class LinkService:
    def __init__(self, session: AsyncSession, repo: LinkRepository) -> None:
        self._session = session
        self._repo = repo

    async def create_link(self, data: LinkCreateRequest) -> LinkResponse:
        is_custom_code = data.short_code is not None

        url = data.original_url
        base = settings.BASE_URL
        base_url = str(base).rstrip("/")  # Убирает лишние слэши

        # URL ведёт на сам сервис
        if url.host == base.host:
            logger.info("Попытка создания петлевой ссылки %s", data.original_url)
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
                logger.info("Создана новая ссылка %s", short_code)
                return LinkResponse(short_url=f"{base_url}/{link.short_code}", expires_at=link.expires_at)
            except IntegrityError as e:
                await self._session.rollback()
                if getattr(e.orig, "sqlstate", None) == "23505":  # Нарушение уникальности
                    if is_custom_code:  # Если пользователь сам ввел занятый код — сразу 409
                        raise ShortCodeAlreadyExistsError from e
                    logger.warning("Коллизия сгенерированного кода %s, попытка %d", short_code, attempt + 1)
                    # Если сгенерированный код совпал с существующим кастомным — след. попытка
                    continue
                raise

        raise ShortCodeGenerationError()

    async def get_target_url(self, short_code: str) -> str:
        logger.info("Переход по ссылке %s", short_code)
        original_url = await self._repo.resolve_and_count(short_code)
        if original_url is None:
            raise LinkNotFoundError(f"Ссылка с кодом {short_code} не найдена или срок её действия истёк")
        await self._session.commit()  # Фиксирует инкремент счетчика в базе данных
        return original_url

    async def get_stats(self, short_code: str) -> LinkStatsResponse:
        link = await self._repo.get_by_short_code(short_code)
        if link is None:
            raise LinkNotFoundError(f"Ссылка с кодом {short_code} не найдена или срок её действия истёк")
        return LinkStatsResponse.model_validate(link)

    async def cleanup_expired_links(self) -> int:
        deleted_count = await self._repo.delete_expired()
        await self._session.commit()
        logger.info("Удалено истекших ссылок: %s", deleted_count)
        return deleted_count
