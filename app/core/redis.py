from functools import lru_cache

import redis.asyncio as aioredis

from app.config import get_settings


@lru_cache
def get_redis_pool() -> aioredis.Redis:
    settings = get_settings()
    return aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=50,
    )


async def get_redis() -> aioredis.Redis:
    return get_redis_pool()
