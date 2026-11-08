import asyncio

from app.core.cache import redis_client
from app.core.database import engine, session_factory
from app.repositories.link import LinkRepository
from app.services.link import LinkService
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.cleanup_expired_links")
def cleanup_expired_links() -> int:
    """
    Запускает асинхронную функцию из синхронной задачи Celery
    asyncio.run() создаёт event loop, необходимый для работы с асинхронной БД
    """
    return asyncio.run(_run())


async def _run() -> int:
    """Удаляет из БД ссылки с истекшим сроком действия и возвращает количество удаленных ссылок"""
    try:
        async with session_factory() as session:
            service = LinkService(session, redis_client, LinkRepository(session))
            return await service.cleanup_expired_links()
    finally:
        await engine.dispose()
