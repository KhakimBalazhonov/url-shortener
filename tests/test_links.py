import re
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Link
from app.repositories.link import LinkRepository
from app.services.link import NOT_FOUND, LinkService

settings = get_settings()


@pytest.mark.parametrize(
    "original_url, short_code, expires_at",
    [
        (
            "https://example.com/",
            None,
            None,
        ),
        (
            "https://example.com/",
            None,
            "2060-01-01T00:00:00.00Z",
        ),
        (
            "https://example.com/",
            "my-code",
            None,
        ),
        (
            "https://example.com/",
            "my-code",
            "2060-01-01T00:00:00.00Z",
        ),
    ],
)
async def test_create_link_success(
    client: AsyncClient,
    original_url: str,
    short_code: str | None,
    expires_at: str | None,
) -> None:
    """Проверка успешного создания ссылки"""
    payload = {
        "original_url": original_url,
        "short_code": short_code,
        "expires_at": expires_at,
    }
    response = await client.post("/shorten", json=payload)
    assert response.status_code == 201, response.text

    link_data = response.json()
    base_url = str(settings.BASE_URL).rstrip("/")
    # Оставляет только короткий код
    extracted_code = link_data["short_url"].removeprefix(base_url).lstrip("/")

    if short_code is not None:
        # Для кастомного кода - возвращенный код строго совпадает с запрошенным
        assert extracted_code == short_code
    else:
        # Автоматический код должен быть длиной от 6 символов и соответствовать Base62-паттерну
        assert len(extracted_code) >= 6
        assert re.fullmatch(r"[a-zA-Z0-9]+", extracted_code)


async def test_short_code_already_exists(client: AsyncClient) -> None:
    """Попытка зарегистрировать уже занятый кастомный код"""
    payload = {"original_url": "https://example.com/", "short_code": "my-code"}

    # Первый запрос
    res1 = await client.post("/shorten", json=payload)
    assert res1.status_code == 201, res1.text

    # Второй запрос с тем же кодом должен быть отклонен
    res2 = await client.post("/shorten", json=payload)
    assert res2.status_code == 409, res2.text
    body = res2.json()
    assert body["error"] == "ShortCodeAlreadyExistsError"


async def test_self_reference_link(client: AsyncClient) -> None:
    """Попытка сократить адрес самого сервиса (защита от петлевых ссылок)"""
    response = await client.post("/shorten", json={"original_url": str(settings.BASE_URL)})
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "SelfReferencingUrlError"


async def test_non_existent_link(client: AsyncClient) -> None:
    """Переход по несуществующему коду возвращает 404"""
    response = await client.get("/non-existent-code")
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "LinkNotFoundError"


async def test_cannot_get_expired_link(
    client: AsyncClient,
    test_db_session: AsyncSession,
) -> None:
    """Просроченная ссылка не редиректит и отдает 404"""
    payload = {
        "original_url": "https://example.com/",
        "short_code": "will-expire",
        "expires_at": "2060-01-01T00:00:00.00Z",
    }
    response = await client.post("/shorten", json=payload)
    assert response.status_code == 201, response.text

    # Изменяет дату на просроченную
    await test_db_session.execute(
        update(Link).where(Link.short_code == "will-expire").values(expires_at=datetime(2010, 1, 1, tzinfo=UTC))
    )
    await test_db_session.commit()

    # Переход отдает 404
    response = await client.get("/will-expire")
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "LinkNotFoundError"


@pytest.mark.parametrize(
    "slug",
    [
        "docs",
        "DOCS",
        "Docs",
        "redoc",
        "REDOC",
        "shorten",
        "api",
        "health",
        "metrics",
    ],
)
async def test_reserved_slugs_validation(client: AsyncClient, slug: str) -> None:
    """Зарезервированные слова отклоняются независимо от регистра"""
    payload = {"original_url": "https://example.com/", "short_code": slug}
    response = await client.post("/shorten", json=payload)
    assert response.status_code == 422, response.text
    assert "detail" in response.json()


async def test_redirect_counts_clicks_in_redis_and_syncs_to_db(
    client: AsyncClient,
    test_db_session: AsyncSession,
    test_redis: Redis,
) -> None:
    """
    Проверка редиректа 302 с корректным Location заголовком
    и инкремент счетчика clicks_count в бд
    """
    payload = {"original_url": "https://example.com/target", "short_code": "my-code"}
    response = await client.post("/shorten", json=payload)
    assert response.status_code == 201, response.text

    # Начальное значение кликов
    initial_db_clicks = await test_db_session.scalar(select(Link.clicks_count).where(Link.short_code == "my-code"))
    assert initial_db_clicks == 0
    assert await test_redis.get("clicks:my-code") is None

    # Переход по ссылке
    response = await client.get("/my-code")
    assert response.status_code == 302, response.text
    assert response.headers["location"] == "https://example.com/target"

    # В Postgres по-прежнему 0
    db_clicks_after_redirect = await test_db_session.scalar(
        select(Link.clicks_count).where(Link.short_code == "my-code")
    )
    assert db_clicks_after_redirect == 0

    # Счетчик кликов в редис
    redis_clicks = await test_redis.get("clicks:my-code")
    assert int(redis_clicks) == 1

    # Эндпоинт статистики сразу видит этот клик в реальном времени
    stats_res = await client.get("/my-code/stats")
    assert stats_res.status_code == 200
    assert stats_res.json()["clicks_count"] == 1

    # Запускает синхронизацию (имитация фонового Celery)
    service = LinkService(test_db_session, test_redis, LinkRepository(test_db_session))
    await service.sync_clicks()

    # Счетчик кликов в бд
    updated_clicks = await test_db_session.scalar(select(Link.clicks_count).where(Link.short_code == "my-code"))
    assert updated_clicks == 1

    # В редис буфер очищен
    assert await test_redis.get("clicks:my-code") is None


async def test_redirect_is_served_from_cache(client: AsyncClient, test_db_session: AsyncSession) -> None:
    """Повторный переход берётся из кеша: ссылка отдаётся, даже если строки в БД уже нет"""
    payload = {"original_url": "https://example.com/cached", "short_code": "cached-code"}
    response = await client.post("/shorten", json=payload)
    assert response.status_code == 201, response.text

    first = await client.get("/cached-code")  # Читает БД и заполняет кеш
    assert first.status_code == 302, first.text

    await test_db_session.execute(delete(Link).where(Link.short_code == "cached-code"))
    await test_db_session.commit()

    second = await client.get("/cached-code")
    assert second.status_code == 302, second.text
    assert second.headers["location"] == "https://example.com/cached"


async def test_not_found_marker_is_reset_on_create(client: AsyncClient, test_redis: Redis) -> None:
    """Метка __NOT_FOUND__ не мешает переходу по только что созданной ссылке"""
    missing = await client.get("/my-code")
    assert missing.status_code == 404, missing.text
    assert await test_redis.get("link:my-code") == NOT_FOUND

    payload = {"original_url": "https://example.com/", "short_code": "my-code"}
    response = await client.post("/shorten", json=payload)
    assert response.status_code == 201, response.text

    response = await client.get("/my-code")
    assert response.status_code == 302, response.text


async def test_get_stats(client: AsyncClient) -> None:
    """Получение аналитики по ссылке"""
    payload = {
        "original_url": "https://example.com/",
        "short_code": "my-code",
        "expires_at": "2060-01-01T00:00:00.00Z",
    }
    response = await client.post("/shorten", json=payload)
    assert response.status_code == 201, response.text

    # Статистика
    response = await client.get("/my-code/stats")
    assert response.status_code == 200, response.text

    stats = response.json()
    assert stats["original_url"] == "https://example.com/"
    assert stats["short_code"] == "my-code"
    assert stats["clicks_count"] == 0
    assert datetime.fromisoformat(stats["created_at"]) < datetime.now(tz=UTC)
    assert datetime.fromisoformat(stats["expires_at"]) > datetime.now(tz=UTC)

    # Несуществующая ссылка
    not_found = await client.get("/missing-code/stats")
    assert not_found.status_code == 404, not_found.text
    assert not_found.json()["error"] == "LinkNotFoundError"


async def test_cannot_get_expired_stats(
    client: AsyncClient,
    test_db_session: AsyncSession,
) -> None:
    """Просроченная ссылка не отдает статистику"""
    payload = {
        "original_url": "https://example.com/",
        "short_code": "will-expire",
        "expires_at": "2060-01-01T00:00:00.00Z",
    }
    response = await client.post("/shorten", json=payload)
    assert response.status_code == 201, response.text

    # Изменяет дату на просроченную
    await test_db_session.execute(
        update(Link).where(Link.short_code == "will-expire").values(expires_at=datetime(2010, 1, 1, tzinfo=UTC))
    )
    await test_db_session.commit()

    response = await client.get("/will-expire/stats")
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "LinkNotFoundError"


@pytest.mark.parametrize(
    "original_url, short_code, expires_at",
    [
        pytest.param("ftp://example.com/file", None, None, id="unsupported_ftp_scheme"),
        pytest.param("javascript:alert(1)", None, None, id="xss_javascript_scheme"),
        pytest.param("https://", None, None, id="empty_host"),
        pytest.param("https://example.com/", "a", None, id="short_code_too_short_min_3"),
        pytest.param("https://example.com/", "a" * 33, None, id="short_code_too_long_max_32"),
        pytest.param("https://example.com/", "my/code", None, id="short_code_slash_forbidden"),
        pytest.param("https://example.com/", "my code", None, id="short_code_space_forbidden"),
        pytest.param(
            "https://example.com/",
            None,
            "2010-01-01T00:00:00.00Z",
            id="expiration_date_in_past",
        ),
        pytest.param(
            "https://example.com/",
            None,
            "2060-01-01T00:00:00.00",
            id="expiration_naive_without_timezone",
        ),
        pytest.param(None, "my-code", "2060-01-01T00:00:00.00Z", id="missing_original_url"),
    ],
)
async def test_create_link_validation_error(
    client: AsyncClient,
    original_url: str | None,
    short_code: str | None,
    expires_at: str | None,
) -> None:
    """Валидация входных данных (422 Unprocessable Entity)"""
    payload = {
        "original_url": original_url,
        "short_code": short_code,
        "expires_at": expires_at,
    }
    response = await client.post("/shorten", json=payload)
    assert response.status_code == 422, response.text
    assert "detail" in response.json()


class MockDBError(Exception):
    """Имитация ошибки драйвера"""

    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


async def test_generated_code_collision_returns_500_after_max_retries(
    client: AsyncClient,
) -> None:
    """При коллизиях сервис делает ровно 5 попыток генерации и возвращает 500 в случае неудачи"""
    with patch(
        "sqlalchemy.ext.asyncio.AsyncSession.commit",
        new_callable=AsyncMock,
        # Имитация ошибки PostgreSQL с кодом sqlstate = "23505" (нарушение уникальности)
        side_effect=IntegrityError(
            statement="INSERT INTO links",
            params={},
            orig=MockDBError("23505"),
        ),
    ) as commit_mock:
        response = await client.post(
            "/shorten",
            json={"original_url": "https://example.com/"},
        )

    # 5 попыток коммита
    assert commit_mock.await_count == 5
    assert response.status_code == 500, response.text
    body = response.json()
    assert body["error"] == "ShortCodeGenerationError"
    assert body["message"] == "Не удалось сгенерировать уникальный код ссылки"


async def test_collision_success_on_retry(client: AsyncClient) -> None:
    """
    Проверка логики после коллизии:
    если первая сгенерированная ссылка совпала с занятой, сервис
    делает второй вызов и успешно сохраняет уникальный код
    """
    # Занимает код taken1 вручную
    await client.post(
        "/shorten",
        json={"original_url": "https://example.com/", "short_code": "taken1"},
    )

    # Имитирует генерацию сначала taken1 (коллизия), а затем unique2 (успех)
    with patch(
        "app.services.link.encode_id",
        side_effect=["taken1", "unique2"],
    ) as mock_encode:
        response = await client.post(
            "/shorten",
            json={"original_url": "https://example.com/"},
        )

    assert response.status_code == 201, response.text
    assert response.json()["short_url"].endswith("/unique2")
    assert mock_encode.call_count == 2


async def test_cleanup_deletes_only_expired_links(
    client: AsyncClient, test_db_session: AsyncSession, test_redis: Redis
) -> None:
    """
    Проверка периодической очистки:
    - Просроченная ссылка удаляется из БД
    - Бессрочная и будущая ссылки остаются
    """
    # Бессрочная ссылка (expires_at = None)
    res1 = await client.post(
        "/shorten",
        json={"original_url": "https://example.com/perm", "short_code": "perm-link"},
    )
    assert res1.status_code == 201, res1.text

    # Временная ссылка с будущим сроком действия (не должна удалиться)
    res2 = await client.post(
        "/shorten",
        json={
            "original_url": "https://example.com/future",
            "short_code": "future-link",
            "expires_at": "2060-01-01T00:00:00.00Z",
        },
    )
    assert res2.status_code == 201, res2.text

    # Временная ссылка с будущим сроком действия, которая позже изменится на истекший
    res3 = await client.post(
        "/shorten",
        json={
            "original_url": "https://example.com/old",
            "short_code": "old-link",
            "expires_at": "2060-01-01T00:00:00.00Z",
        },
    )
    assert res3.status_code == 201, res3.text

    # Состаривает третью ссылку
    await test_db_session.execute(
        update(Link).where(Link.short_code == "old-link").values(expires_at=datetime(2010, 1, 1, tzinfo=UTC))
    )
    await test_db_session.commit()

    # Запуск очистки
    service = LinkService(test_db_session, test_redis, LinkRepository(test_db_session))
    deleted_count = await service.cleanup_expired_links()
    assert deleted_count == 1

    # Просроченная ссылка удалена
    assert await test_db_session.scalar(select(Link).where(Link.short_code == "old-link")) is None

    # Будущая и бессрочная ссылки остались
    assert await test_db_session.scalar(select(Link).where(Link.short_code == "future-link")) is not None
    assert await test_db_session.scalar(select(Link).where(Link.short_code == "perm-link")) is not None
