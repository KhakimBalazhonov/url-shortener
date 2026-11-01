import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from app.api.link import router
from app.core.config import get_settings
from app.core.database import engine
from app.core.exceptions import AppException
from app.core.logger import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    logger.info("Приложение '%s' запущено (режим отладки=%s)", settings.APP_NAME, settings.DEBUG)
    try:
        yield
    finally:
        await engine.dispose()
        logger.info("Приложение остановлено")


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


@app.exception_handler(AppException)
async def business_error_handler(_: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.__class__.__name__, "message": exc.message},
    )


app.include_router(router)
