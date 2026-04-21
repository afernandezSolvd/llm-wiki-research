import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import Role, require_role
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.core.storage import get_storage
from app.dependencies import get_current_user
from app.models.source import Source
from app.models.user import User

router = APIRouter(prefix="/workspaces/{workspace_id}/sources", tags=["sources"])


class SourceResponse(BaseModel):
    id: uuid.UUID
    title: str
    source_type: str
    ingest_status: str
    byte_size: int | None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[SourceResponse])
async def list_sources(
    workspace_id: uuid.UUID,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)
    q = (
        select(Source)
        .where(Source.workspace_id == workspace_id)
        .order_by(Source.created_at.desc())
        .limit(min(limit, 200))
        .offset(offset)
    )
    if status_filter:
        q = q.where(Source.ingest_status == status_filter)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def upload_source(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    title: Annotated[str, Form()] = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.editor)

    data = await file.read()
    storage = get_storage()
    storage_key, content_hash = await storage.upload(
        data, file.filename or "upload", file.content_type or "application/octet-stream"
    )

    # Detect type from content-type
    ct = file.content_type or ""
    if "pdf" in ct:
        source_type = "pdf"
    elif "text" in ct or ct == "":
        source_type = "text"
    elif "image" in ct:
        source_type = "image"
    else:
        source_type = "text"

    # Check for duplicate by content_hash — return existing source instead of erroring
    existing = await db.execute(select(Source).where(Source.content_hash == content_hash))
    dup = existing.scalar_one_or_none()
    if dup:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "id": str(dup.id),
                "title": dup.title,
                "source_type": dup.source_type,
                "ingest_status": dup.ingest_status,
                "byte_size": dup.byte_size,
                "_note": "Duplicate file — returning existing source",
            },
        )

    source = Source(
        workspace_id=workspace_id,
        title=title or file.filename or "Untitled",
        source_type=source_type,
        storage_key=storage_key,
        content_hash=content_hash,
        byte_size=len(data),
        ingest_status="pending",
        created_by=current_user.id,
    )
    db.add(source)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Race condition: another request committed the same hash between our check and insert
        existing2 = await db.execute(select(Source).where(Source.content_hash == content_hash))
        source = existing2.scalar_one()
    await db.refresh(source)
    return source


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)
    source = await db.get(Source, source_id)
    if not source or source.workspace_id != workspace_id:
        raise NotFoundError("Source", str(source_id))
    return source


class UrlSourceCreate(BaseModel):
    url: str
    title: str = ""


@router.post("/from-url", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def ingest_from_url(
    workspace_id: uuid.UUID,
    body: UrlSourceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a URL and create a source from its content."""
    await require_role(db, current_user, workspace_id, Role.editor)

    import hashlib
    import httpx

    fetch_url = _normalize_url(body.url)

    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as http:
        resp = await http.get(fetch_url)
        resp.raise_for_status()
        data = resp.content
        content_type = resp.headers.get("content-type", "text/html")

    content_hash = hashlib.sha256(data).hexdigest()
    existing = await db.execute(select(Source).where(Source.content_hash == content_hash))
    if dup := existing.scalar_one_or_none():
        return dup

    storage = get_storage()
    filename = body.url.rstrip("/").split("/")[-1] or "page.html"
    storage_key, _ = await storage.upload(data, filename, content_type)

    source_type = "pdf" if "pdf" in content_type else "url"
    source = Source(
        workspace_id=workspace_id,
        title=body.title or body.url,
        source_type=source_type,
        storage_key=storage_key,
        content_hash=content_hash,
        byte_size=len(data),
        metadata_={"url": body.url},
        ingest_status="pending",
        created_by=current_user.id,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


def _normalize_url(url: str) -> str:
    """Rewrite well-known rendered URLs to their raw/plain-text equivalents."""
    import re
    # GitHub Gist: https://gist.github.com/{user}/{id} → raw content
    m = re.match(r"https://gist\.github\.com/([^/]+/[a-f0-9]+)(?:/.*)?$", url)
    if m:
        return f"https://gist.githubusercontent.com/{m.group(1)}/raw"
    # GitHub file view: https://github.com/{user}/{repo}/blob/{ref}/{path}
    m = re.match(r"https://github\.com/(.+)/blob/(.+)", url)
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}"
    return url


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.editor)
    source = await db.get(Source, source_id)
    if not source or source.workspace_id != workspace_id:
        raise NotFoundError("Source", str(source_id))
    await db.delete(source)
    await db.commit()
