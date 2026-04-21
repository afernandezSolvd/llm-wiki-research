"""
Prompt cache key management.

Cache hierarchy (most stable first — cached blocks must come before uncached):
  Block 1: schema.md content   (rarely changes, cached)
  Block 2: hot wiki pages      (changes on ingest, cached, rebuilt every 15 min)
  Block 3: per-request context (never cached)

Anthropic caches the LONGEST matching prefix, so stable blocks must be first.
"""
import uuid

import redis.asyncio as aioredis

from app.config import get_settings
from app.core.logging import get_logger
from app.llm.client import make_cached_block, make_text_block

logger = get_logger(__name__)
settings = get_settings()

_SCHEMA_CACHE_KEY = "prompt_cache:schema:{workspace_id}"
_HOT_PAGES_CACHE_KEY = "prompt_cache:hot_pages:{workspace_id}"
_HOT_PAGES_DIRTY_KEY = "prompt_cache:hot_pages:{workspace_id}:dirty"


async def get_schema_block(
    redis: aioredis.Redis,
    workspace_id: uuid.UUID,
    schema_content: str,
) -> dict:
    """Return the cached schema block. Always the same content — just wraps it."""
    return make_cached_block(f"<schema>\n{schema_content}\n</schema>")


async def get_hot_pages_block(
    redis: aioredis.Redis,
    workspace_id: uuid.UUID,
    page_contents: list[tuple[str, str]],  # [(title, content), ...]
) -> dict:
    """
    Build and cache the hot-pages block.
    page_contents should be the top-N most queried wiki pages.
    """
    combined = "\n\n---\n\n".join(
        f"## {title}\n\n{content}" for title, content in page_contents
    )
    block_text = f"<wiki_hot_pages>\n{combined}\n</wiki_hot_pages>"

    # Store in Redis so workers can check staleness
    cache_key = _HOT_PAGES_CACHE_KEY.format(workspace_id=workspace_id)
    await redis.setex(cache_key, settings.hot_pages_cache_ttl_seconds, block_text)

    return make_cached_block(block_text)


async def mark_hot_pages_dirty(redis: aioredis.Redis, workspace_id: uuid.UUID) -> None:
    """Called after ingest touches pages that are in the hot-pages set."""
    dirty_key = _HOT_PAGES_DIRTY_KEY.format(workspace_id=workspace_id)
    await redis.set(dirty_key, "1", ex=settings.hot_pages_cache_ttl_seconds)


async def is_hot_pages_dirty(redis: aioredis.Redis, workspace_id: uuid.UUID) -> bool:
    dirty_key = _HOT_PAGES_DIRTY_KEY.format(workspace_id=workspace_id)
    return bool(await redis.exists(dirty_key))


async def increment_page_query_count(
    redis: aioredis.Redis, workspace_id: uuid.UUID, page_id: uuid.UUID
) -> None:
    """Track how many times a page appears in query results (for hot-page ranking)."""
    key = f"prompt_cache:page_hits:{workspace_id}"
    await redis.zincrby(key, 1, str(page_id))


async def get_top_page_ids(
    redis: aioredis.Redis, workspace_id: uuid.UUID, top_n: int
) -> list[uuid.UUID]:
    """Return top-N most-queried page IDs."""
    key = f"prompt_cache:page_hits:{workspace_id}"
    ids = await redis.zrevrange(key, 0, top_n - 1)
    return [uuid.UUID(i) for i in ids]
