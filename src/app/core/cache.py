from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()

redis_client = Redis.from_url(
    settings.cache_url,
    # Redis возвращает данные в формате bytes, decode_responses преобразует их в строки
    decode_responses=True,
)
