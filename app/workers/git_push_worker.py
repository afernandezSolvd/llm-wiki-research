import asyncio
import uuid

from app.core.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


def _run(coro):
    return asyncio.run(coro)


@celery_app.task(
    name="app.workers.git_push_worker.push_to_remote",
    bind=True,
    max_retries=6,
)
def push_to_remote(self, workspace_id: str):
    try:
        _run(_push_async(workspace_id))
    except _LockUnavailable as exc:
        raise self.retry(exc=exc, countdown=10)
    except Exception as exc:
        logger.error(
            "git_push_error",
            workspace_id=workspace_id,
            error=str(exc),
            attempt=self.request.retries + 1,
        )
        raise self.retry(exc=exc, countdown=10)


async def _push_async(workspace_id: str):
    from datetime import UTC, datetime

    import redis.asyncio as aioredis
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import get_settings
    from app.git.repo_manager import RepoManager
    from app.models.workspace import Workspace

    settings = get_settings()

    if not settings.wiki_git_enabled:
        return

    _engine = create_async_engine(settings.database_url, poolclass=NullPool)
    _Session = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )

    async with _Session() as db:
        result = await db.execute(
            select(Workspace).where(Workspace.id == uuid.UUID(workspace_id))
        )
        workspace = result.scalar_one_or_none()
        if workspace is None or workspace.git_remote_url is None:
            return

    lock_key = f"git_push_lock:{workspace_id}"
    redis_client = aioredis.from_url(settings.redis_url)
    lock_held = False

    try:
        lock_held = bool(await redis_client.set(lock_key, "1", nx=True, px=120000))
        if not lock_held:
            raise _LockUnavailable(f"Push lock held for workspace {workspace_id}")

        logger.info("git_push_start", workspace_id=workspace_id)

        try:
            repo = RepoManager(uuid.UUID(workspace_id))
            sha = repo.push_to_remote(settings.wiki_git_provider_token)

            async with _Session() as db:
                result = await db.execute(
                    select(Workspace).where(Workspace.id == uuid.UUID(workspace_id))
                )
                ws = result.scalar_one_or_none()
                if ws is not None:
                    ws.git_last_push_at = datetime.now(UTC)
                    ws.git_last_push_error = None
                    await db.commit()

            logger.info("git_push_success", workspace_id=workspace_id, sha=sha[:8])

        except Exception as exc:
            async with _Session() as db:
                result = await db.execute(
                    select(Workspace).where(Workspace.id == uuid.UUID(workspace_id))
                )
                ws = result.scalar_one_or_none()
                if ws is not None:
                    ws.git_last_push_error = str(exc)
                    await db.commit()
            raise

    finally:
        if lock_held:
            await redis_client.delete(lock_key)
        await redis_client.aclose()
        _engine.dispose()


class _LockUnavailable(Exception):
    pass
