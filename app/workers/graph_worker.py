"""Celery tasks for KG community detection and hot-pages cache refresh."""
import asyncio
import uuid
from datetime import UTC, datetime

from app.workers.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


def _run(coro):
    return asyncio.run(coro)


@celery_app.task(name="app.workers.graph_worker.maybe_rebuild_communities")
def maybe_rebuild_communities(workspace_id_str: str):
    """Rebuild KG communities if debounce period has passed."""
    _run(_maybe_rebuild_async(uuid.UUID(workspace_id_str)))


async def _maybe_rebuild_async(workspace_id: uuid.UUID):
    from app.core.redis import get_redis_pool
    from app.config import get_settings

    settings = get_settings()
    redis = get_redis_pool()

    debounce_key = f"kg:community_rebuild_lock:{workspace_id}"
    acquired = await redis.set(
        debounce_key,
        "1",
        nx=True,
        ex=settings.kg_community_rebuild_debounce_minutes * 60,
    )
    if not acquired:
        logger.info("kg_community_rebuild_debounced", workspace_id=str(workspace_id))
        return

    from app.core.db import AsyncSessionLocal
    from app.models.knowledge_graph import KGEdge
    from app.services.graph_service import rebuild_communities, MAX_EDGES_FOR_COMMUNITY_DETECTION
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as db:
        # Warn operators if we're going to sample (graph too large for full Louvain)
        count_result = await db.execute(
            select(func.count(KGEdge.id)).where(KGEdge.workspace_id == workspace_id)
        )
        edge_count = count_result.scalar() or 0
        if edge_count > MAX_EDGES_FOR_COMMUNITY_DETECTION:
            logger.warning(
                "kg_graph_exceeds_full_louvain_capacity",
                workspace_id=str(workspace_id),
                edge_count=edge_count,
                cap=MAX_EDGES_FOR_COMMUNITY_DETECTION,
                note="Community detection running on top-weight edges only. "
                     "Consider migrating to a dedicated graph DB for full coverage.",
            )

        count = await rebuild_communities(db, workspace_id)
        logger.info("kg_communities_rebuilt", workspace_id=str(workspace_id), count=count)


@celery_app.task(name="app.workers.graph_worker.refresh_hot_pages_all_workspaces")
def refresh_hot_pages_all_workspaces():
    """Beat task: refresh hot-pages cache for all active workspaces."""
    _run(_refresh_hot_pages_async())


async def _refresh_hot_pages_async():
    from app.core.db import AsyncSessionLocal
    from app.core.redis import get_redis_pool
    from app.config import get_settings
    from app.models.workspace import Workspace
    from app.models.wiki_page import WikiPage
    from app.llm.prompt_cache import (
        get_top_page_ids, get_hot_pages_block, is_hot_pages_dirty
    )
    from app.git.repo_manager import RepoManager
    from sqlalchemy import select

    settings = get_settings()
    redis = get_redis_pool()

    async with AsyncSessionLocal() as db:
        workspaces_result = await db.execute(
            select(Workspace).where(Workspace.deleted_at.is_(None))
        )
        workspaces = workspaces_result.scalars().all()

        for ws in workspaces:
            if not await is_hot_pages_dirty(redis, ws.id):
                continue  # Cache is still fresh

            top_ids = await get_top_page_ids(redis, ws.id, settings.hot_pages_cache_top_n)
            hot_pages: list[tuple[str, str]] = []
            for pid in top_ids:
                page = await db.get(WikiPage, pid)
                if page:
                    repo = RepoManager(ws.id)
                    content = repo.read_file(page.page_path) or ""
                    hot_pages.append((page.title, content[:1500]))

            if hot_pages:
                await get_hot_pages_block(redis, ws.id, hot_pages)
                logger.info("hot_pages_cache_refreshed", workspace_id=str(ws.id), count=len(hot_pages))
