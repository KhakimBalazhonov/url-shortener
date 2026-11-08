from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from app.core.cache import get_redis
from app.core.database import get_db
from app.main import app


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """Запускает изолированный контейнер Postgres на всю сессию тестов"""
    with PostgresContainer("postgres:18-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def migrated_db(pg_url: str) -> None:
    """Применяет миграции Alembic к тестовой БД до старта тестов"""
    # Подключает Alembic к тестовой БД
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", pg_url)

    # Применяет все миграции
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
async def test_engine(pg_url: str, migrated_db: None) -> AsyncIterator[AsyncEngine]:
    """Асинхронный движок SQLAlchemy для тестовой БД"""
    engine = create_async_engine(pg_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def test_db_connection(test_engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """
    Открывает соединение и транзакцию
    После каждого теста откатывает транзакцию, гарантируя изоляцию
    """
    async with test_engine.connect() as conn:
        transaction = await conn.begin()
        try:
            yield conn
        finally:
            await transaction.rollback()


@pytest.fixture
def test_session_factory(
    test_db_connection: AsyncConnection,
) -> async_sessionmaker[AsyncSession]:
    """Фабрика сессий"""
    return async_sessionmaker(
        bind=test_db_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",  # commit() в тесте не сломает откат
    )


@pytest.fixture
async def test_db_session(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Тестовая сессия базы данных"""
    async with test_session_factory() as session:
        yield session


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    """Запускает изолированный контейнер Redis на сессию тестов"""
    with RedisContainer("redis:7-alpine") as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}/1"


@pytest.fixture
async def test_redis(redis_url: str) -> AsyncIterator[Redis]:
    """Клиент Redis для тестов"""
    redis = Redis.from_url(redis_url, decode_responses=True)
    await redis.flushdb()  # кеш не должен переходить из теста в тест
    yield redis
    await redis.aclose()


@pytest.fixture
async def client(test_db_session: AsyncSession, test_redis: Redis) -> AsyncIterator[AsyncClient]:
    """Тестовый HTTP-клиент с подменой базы и кеша"""

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield test_db_session

    async def _override_get_redis() -> AsyncIterator[Redis]:
        yield test_redis

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis] = _override_get_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
