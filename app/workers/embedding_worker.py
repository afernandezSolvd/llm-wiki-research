"""Celery task: embed a source chunk (used for parallel subtask dispatch)."""
import asyncio
import uuid
from datetime import UTC, datetime

from app.workers.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


def _run(coro):
    return asyncio.run(coro)


@celery_app.task(name="app.workers.embedding_worker.embed_source_chunk")
def embed_source_chunk(chunk_id: str):
    _run(_embed_chunk_async(uuid.UUID(chunk_id)))


async def _embed_chunk_async(chunk_id: uuid.UUID):
    from app.core.db import AsyncSessionLocal
    from app.models.source import SourceChunk
    from app.services.embedding_service import get_embedding_service

    svc = get_embedding_service()
    async with AsyncSessionLocal() as db:
        chunk = await db.get(SourceChunk, chunk_id)
        if not chunk or chunk.embedding:
            return
        embedding = await svc.embed_single(chunk.chunk_text)
        chunk.embedding = embedding
        await db.commit()
