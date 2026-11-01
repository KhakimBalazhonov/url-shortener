import asyncio

from app.core.database import engine, session_factory
from app.repositories.link import LinkRepository
from app.services.link import LinkService
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.cleanup_expired_links")
def cleanup_expired_links() -> int:
    return asyncio.run(_run())


async def _run() -> int:
    try:
        async with session_factory() as session:
            service = LinkService(session, LinkRepository(session))
            deleted_count = await service.cleanup_expired_links()
            return deleted_count
    finally:
        await engine.dispose()
