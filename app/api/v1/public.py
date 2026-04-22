"""Public read-only portal API — no authentication required.

All routes return HTTP 503 when settings.public_api_enabled is False.
This router should only be reachable on a trusted internal network.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.git.repo_manager import RepoManager
from app.models.source import Source
from app.models.wiki_page import WikiPage, WikiPageSourceMap
from app.models.workspace import Workspace

logger = get_logger(__name__)
router = APIRouter(prefix="/public", tags=["public"])

_DISABLED = JSONResponse(
    status_code=503,
    content={"detail": "Public portal API is disabled"},
)


def _guard() -> None:
    settings = get_settings()
    if not settings.public_api_enabled:
        raise _DISABLED  # type: ignore[raise]


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class WorkspacePublicResponse(BaseModel):
    id: uuid.UUID
    slug: str
    display_name: str
    schema_version: int

    model_config = {"from_attributes": True}


class WikiPagePublicResponse(BaseModel):
    id: uuid.UUID
    page_path: str
    title: str
    page_type: str
    word_count: int | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class WikiPageDetailPublicResponse(WikiPagePublicResponse):
    content: str


class SourcePublicResponse(BaseModel):
    id: uuid.UUID
    title: str
    source_type: str
    ingest_status: str
    byte_size: int | None
    created_at: datetime | None

    model_config = {"from_attributes": True}


class SearchResultItem(BaseModel):
    id: uuid.UUID
    page_path: str
    title: str
    snippet: str
    updated_at: datetime | None


class SearchResponse(BaseModel):
    total_count: int
    results: list[SearchResultItem]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_workspace_or_404(workspace_id: uuid.UUID, db: AsyncSession) -> Workspace:
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.deleted_at.is_(None),
        )
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise NotFoundError("Workspace", str(workspace_id))
    return ws


def _make_snippet(content: str, q: str, length: int = 300) -> str:
    lower = content.lower()
    idx = lower.find(q.lower())
    if idx == -1:
        return content[:length]
    start = max(0, idx - 80)
    end = min(len(content), start + length)
    snippet = content[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(content):
        snippet = snippet + "…"
    return snippet


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/workspaces", response_model=list[WorkspacePublicResponse])
async def list_workspaces(db: AsyncSession = Depends(get_db)) -> list[Workspace]:
    _guard()
    logger.info("public_api_request", endpoint="list_workspaces")
    result = await db.execute(
        select(Workspace).where(Workspace.deleted_at.is_(None)).order_by(Workspace.display_name)
    )
    return result.scalars().all()  # type: ignore[return-value]


@router.get("/workspaces/{workspace_id}/pages", response_model=list[WikiPagePublicResponse])
async def list_pages(
    workspace_id: uuid.UUID,
    page_type: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[WikiPage]:
    _guard()
    logger.info("public_api_request", endpoint="list_pages", workspace_id=str(workspace_id))
    await _get_workspace_or_404(workspace_id, db)
    q = (
        select(WikiPage)
        .where(WikiPage.workspace_id == workspace_id)
        .order_by(WikiPage.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if page_type:
        q = q.where(WikiPage.page_type == page_type)
    result = await db.execute(q)
    return result.scalars().all()  # type: ignore[return-value]


@router.get(
    "/workspaces/{workspace_id}/pages/{page_path:path}",
    response_model=WikiPageDetailPublicResponse,
)
async def get_page(
    workspace_id: uuid.UUID,
    page_path: str,
    db: AsyncSession = Depends(get_db),
) -> WikiPageDetailPublicResponse:
    _guard()
    logger.info(
        "public_api_request", endpoint="get_page",
        workspace_id=str(workspace_id), page_path=page_path,
    )
    await _get_workspace_or_404(workspace_id, db)
    result = await db.execute(
        select(WikiPage).where(
            WikiPage.workspace_id == workspace_id,
            WikiPage.page_path == page_path,
        )
    )
    page = result.scalar_one_or_none()
    if not page:
        raise NotFoundError("WikiPage", page_path)
    repo = RepoManager(workspace_id)
    content = repo.read_file(page.page_path) or ""
    return WikiPageDetailPublicResponse(**page.__dict__, content=content)


@router.get("/workspaces/{workspace_id}/sources", response_model=list[SourcePublicResponse])
async def list_sources(
    workspace_id: uuid.UUID,
    status_filter: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[Source]:
    _guard()
    logger.info("public_api_request", endpoint="list_sources", workspace_id=str(workspace_id))
    await _get_workspace_or_404(workspace_id, db)
    q = (
        select(Source)
        .where(Source.workspace_id == workspace_id)
        .order_by(Source.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter:
        q = q.where(Source.ingest_status == status_filter)
    result = await db.execute(q)
    return result.scalars().all()  # type: ignore[return-value]


@router.get(
    "/workspaces/{workspace_id}/sources/{source_id}/pages",
    response_model=list[WikiPagePublicResponse],
)
async def get_source_pages(
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[WikiPage]:
    _guard()
    logger.info(
        "public_api_request", endpoint="get_source_pages",
        workspace_id=str(workspace_id), source_id=str(source_id),
    )
    await _get_workspace_or_404(workspace_id, db)
    source = await db.get(Source, source_id)
    if not source or source.workspace_id != workspace_id:
        raise NotFoundError("Source", str(source_id))
    result = await db.execute(
        select(WikiPage)
        .join(WikiPageSourceMap, WikiPageSourceMap.wiki_page_id == WikiPage.id)
        .where(WikiPageSourceMap.source_id == source_id)
        .order_by(WikiPage.updated_at.desc())
    )
    return result.scalars().all()  # type: ignore[return-value]


@router.get("/workspaces/{workspace_id}/search", response_model=SearchResponse)
async def search_pages(
    workspace_id: uuid.UUID,
    q: str = Query(min_length=2),
    limit: int = Query(default=20, le=50),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    _guard()
    logger.info("public_api_request", endpoint="search_pages", workspace_id=str(workspace_id), q=q)
    await _get_workspace_or_404(workspace_id, db)

    # Search title in wiki_pages and latest content in wiki_page_versions.
    # Title matches are ranked first, then ordered by recency.
    stmt = text(
        """
        SELECT DISTINCT ON (wp.id)
               wp.id, wp.page_path, wp.title, wp.page_type, wp.word_count, wp.updated_at,
               CASE WHEN wp.title ILIKE :pattern THEN 0 ELSE 1 END AS rank
        FROM wiki_pages wp
        WHERE wp.workspace_id = :wid
          AND (
            wp.title ILIKE :pattern
            OR EXISTS (
              SELECT 1 FROM wiki_page_versions wpv
              WHERE wpv.wiki_page_id = wp.id
                AND wpv.content ILIKE :pattern
              LIMIT 1
            )
          )
        ORDER BY wp.id, rank, wp.updated_at DESC
        LIMIT :lim
        """
    ).bindparams(wid=workspace_id, pattern=f"%{q}%", lim=limit)

    rows = (await db.execute(stmt)).mappings().all()

    repo = RepoManager(workspace_id)
    items: list[SearchResultItem] = []
    for row in rows:
        content = repo.read_file(row["page_path"]) or ""
        snippet = _make_snippet(content, q)
        items.append(
            SearchResultItem(
                id=row["id"],
                page_path=row["page_path"],
                title=row["title"],
                snippet=snippet,
                updated_at=row["updated_at"],
            )
        )

    return SearchResponse(total_count=len(items), results=items)
