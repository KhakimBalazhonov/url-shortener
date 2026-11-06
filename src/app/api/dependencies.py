from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_redis
from app.core.database import get_db
from app.repositories.link import LinkRepository
from app.services.link import LinkService

SessionDep = Annotated[AsyncSession, Depends(get_db)]

RedisDep = Annotated[Redis, Depends(get_redis)]


def get_link_repo(session: SessionDep) -> LinkRepository:
    return LinkRepository(session=session)


LinkRepoDep = Annotated[LinkRepository, Depends(get_link_repo)]


def get_link_service(session: SessionDep, redis_client: RedisDep, repo: LinkRepoDep) -> LinkService:
    return LinkService(session=session, redis_client=redis_client, repo=repo)


LinkServiceDep = Annotated[LinkService, Depends(get_link_service)]
