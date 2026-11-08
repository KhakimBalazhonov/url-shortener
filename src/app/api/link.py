from fastapi import APIRouter, status
from starlette.responses import RedirectResponse

from app.api.dependencies import LinkServiceDep
from app.schemas.link import LinkCreateRequest, LinkResponse, LinkStatsResponse

router = APIRouter(tags=["Ссылки"])


@router.post(
    "/shorten",
    status_code=status.HTTP_201_CREATED,
    summary="Создать короткую ссылку",
    responses={
        400: {"description": "Попытка сократить адрес самого сервиса"},
        409: {"description": "Кастомный код уже занят"},
    },
)
async def create_link(data: LinkCreateRequest, service: LinkServiceDep) -> LinkResponse:
    """Создает короткую ссылку с опциональным алиасом и сроком действия"""
    return await service.create_link(data)


@router.get(
    "/{short_code}",
    status_code=status.HTTP_302_FOUND,
    summary="Перейти по короткой ссылке",
    responses={
        404: {"description": "Ссылка не найдена или срок ее действия истек"},
    },
)
async def get_original_url(short_code: str, service: LinkServiceDep) -> RedirectResponse:
    """
    Перенаправляет на исходный URL и увеличивает количество переходов.
    Swagger UI не позволяет корректно проверить редирект на внешний адрес.
    Для проверки необходимо открыть короткую ссылку в браузере.
    """
    original_url = await service.get_target_url(short_code)
    return RedirectResponse(url=original_url, status_code=status.HTTP_302_FOUND)


@router.get(
    "/{short_code}/stats",
    summary="Получить статистику ссылки",
    responses={
        404: {"description": "Ссылка не найдена или срок ее действия истек"},
    },
)
async def get_stats(short_code: str, service: LinkServiceDep) -> LinkStatsResponse:
    """Возвращает количество переходов и метаданные ссылки"""
    return await service.get_stats(short_code)
