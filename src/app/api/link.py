from fastapi import APIRouter, status
from starlette.responses import RedirectResponse

from app.api.dependencies import LinkServiceDep
from app.schemas.link import LinkCreateRequest, LinkResponse

router = APIRouter()


@router.post("/shorten", status_code=status.HTTP_201_CREATED, response_model_exclude_none=True)
async def create_link(data: LinkCreateRequest, service: LinkServiceDep) -> LinkResponse:
    return await service.create_link(data)


@router.get("/{short_code}", status_code=status.HTTP_302_FOUND)
async def get_original_url(short_code: str, service: LinkServiceDep) -> RedirectResponse:
    original_url = await service.get_target_url(short_code)
    return RedirectResponse(url=original_url, status_code=status.HTTP_302_FOUND)
