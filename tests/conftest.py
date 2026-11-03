from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.community.postgres import PostgresContainer

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
    После каждого теста откатывает транзакцию, гарантируя изоляцию.
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


@pytest.fixture
async def client(test_db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield test_db_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
