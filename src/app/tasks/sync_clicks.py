import asyncio

from app.core.cache import redis_client
from app.core.database import engine, session_factory
from app.repositories.link import LinkRepository
from app.services.link import LinkService
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.sync_clicks")
def sync_clicks() -> int:
    """
    Запускает асинхронную функцию из синхронной задачи Celery
    asyncio.run() создаёт event loop, необходимый для работы с асинхронной БД
    """
    return asyncio.run(_run())


async def _run() -> int:
    """Сохраняет накопленные клики из Redis в БД и возвращает количество обновленных ссылок"""
    try:
        async with session_factory() as session:
            service = LinkService(session, redis_client, LinkRepository(session))
            return await service.sync_clicks()
    finally:
        await engine.dispose()
        # В этой задаче используется Redis: если не закрыть соединение, следующий запуск упадёт с "Event loop is closed"
        await redis_client.aclose()
