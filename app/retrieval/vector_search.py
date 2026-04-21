"""pgvector ANN search over source_chunks and wiki_pages."""
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

EMBEDDING_DIM = 1024


@dataclass
class SearchHit:
    page_id: uuid.UUID | None
    chunk_id: uuid.UUID | None
    page_path: str | None
    title: str | None
    excerpt: str
    score: float  # cosine similarity (higher = better)
    source: str  # "wiki_page" | "source_chunk"


async def search_wiki_pages(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int = 15,
) -> list[SearchHit]:
    """Find top-k wiki pages by cosine similarity."""
    vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    result = await db.execute(
        text(
            """
            SELECT
                id,
                page_path,
                title,
                1 - (embedding <=> cast(:embedding as vector)) AS score
            FROM wiki_pages
            WHERE workspace_id = :workspace_id
              AND embedding IS NOT NULL
            ORDER BY embedding <=> cast(:embedding as vector)
            LIMIT :top_k
            """
        ),
        {"embedding": vec_str, "workspace_id": workspace_id, "top_k": top_k},
    )
    rows = result.fetchall()
    return [
        SearchHit(
            page_id=row.id,
            chunk_id=None,
            page_path=row.page_path,
            title=row.title,
            excerpt="",
            score=float(row.score),
            source="wiki_page",
        )
        for row in rows
    ]


async def search_source_chunks(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int = 15,
) -> list[SearchHit]:
    """Find top-k source chunks by cosine similarity."""
    vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    result = await db.execute(
        text(
            """
            SELECT
                sc.id AS chunk_id,
                sc.chunk_text,
                s.title,
                1 - (sc.embedding <=> cast(:embedding as vector)) AS score
            FROM source_chunks sc
            JOIN sources s ON s.id = sc.source_id
            WHERE sc.workspace_id = :workspace_id
              AND sc.embedding IS NOT NULL
            ORDER BY sc.embedding <=> cast(:embedding as vector)
            LIMIT :top_k
            """
        ),
        {"embedding": vec_str, "workspace_id": workspace_id, "top_k": top_k},
    )
    rows = result.fetchall()
    return [
        SearchHit(
            page_id=None,
            chunk_id=row.chunk_id,
            page_path=None,
            title=row.title,
            excerpt=row.chunk_text[:500],
            score=float(row.score),
            source="source_chunk",
        )
        for row in rows
    ]
