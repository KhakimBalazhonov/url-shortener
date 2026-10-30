import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import engine
from app.core.logger import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    logger.info("Application '%s' started (debug=%s)", settings.APP_NAME, settings.DEBUG)
    yield
    await engine.dispose()
    logger.info("Application stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    return FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None if settings.is_prod else "/redoc",
        openapi_url=None if settings.is_prod else "/openapi.json",
    )


app = create_app()
