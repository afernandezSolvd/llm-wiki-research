"""Token-bucket rate limiting per user via Redis."""
import time
import uuid

import redis.asyncio as aioredis
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings
from app.core.redis import get_redis_pool

settings = get_settings()

# Endpoint-specific limits (requests per minute)
ENDPOINT_LIMITS: dict[str, int] = {
    "/ingest": settings.rate_limit_ingest,
    "/query": settings.rate_limit_query,
    "/lint": settings.rate_limit_lint,
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Extract user ID from JWT (best effort; skip on auth errors)
        user_id = _extract_user_id(request)
        if user_id is None:
            return await call_next(request)

        # Determine limit for this endpoint
        path = request.url.path
        limit = settings.rate_limit_default
        for pattern, lim in ENDPOINT_LIMITS.items():
            if pattern in path:
                limit = lim
                break

        redis = get_redis_pool()
        key = f"rate:{user_id}:{path}"
        now = int(time.time())
        window = 60  # 1-minute window

        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        results = await pipe.execute()
        count = results[0]

        if count > limit:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded: {limit} requests/min for this endpoint"},
            )

        return await call_next(request)


def _extract_user_id(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        from app.auth.jwt import decode_token
        uid = decode_token(auth[7:])
        return str(uid)
    except Exception:
        return None
