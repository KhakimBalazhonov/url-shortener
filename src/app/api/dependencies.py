from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.link import LinkRepository
from app.services.link import LinkService

SessionDep = Annotated[AsyncSession, Depends(get_db)]


def get_link_repo(session: SessionDep) -> LinkRepository:
    return LinkRepository(session=session)


LinkRepoDep = Annotated[LinkRepository, Depends(get_link_repo)]


def get_link_service(session: SessionDep, repo: LinkRepoDep) -> LinkService:
    return LinkService(session=session, repo=repo)


LinkServiceDep = Annotated[LinkService, Depends(get_link_service)]
