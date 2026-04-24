"""Wiki pages CRUD + history + rollback endpoints."""
import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import Role, require_role
from app.config import get_settings
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.dependencies import get_current_user
from app.git.repo_manager import RepoManager
from app.models.user import User
from app.models.wiki_page import WikiPage, WikiPageVersion
from app.services.embedding_service import get_embedding_service

router = APIRouter(prefix="/workspaces/{workspace_id}/wiki", tags=["wiki"])


class WikiPageResponse(BaseModel):
    id: uuid.UUID
    page_path: str
    title: str
    page_type: str
    word_count: int | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class WikiPageDetail(WikiPageResponse):
    content: str


class WikiPageCreate(BaseModel):
    page_path: str
    title: str
    page_type: str
    content: str


class WikiPageUpdate(BaseModel):
    content: str
    title: str | None = None


class RollbackRequest(BaseModel):
    commit_sha: str


@router.get("/pages", response_model=list[WikiPageResponse])
async def list_pages(
    workspace_id: uuid.UUID,
    page_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)
    q = (
        select(WikiPage)
        .where(WikiPage.workspace_id == workspace_id)
        .order_by(WikiPage.updated_at.desc())
        .limit(min(limit, 200))
        .offset(offset)
    )
    if page_type:
        q = q.where(WikiPage.page_type == page_type)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/pages", response_model=WikiPageDetail, status_code=status.HTTP_201_CREATED)
async def create_page(
    workspace_id: uuid.UUID,
    body: WikiPageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.editor)

    repo = RepoManager(workspace_id)
    sha = repo.write_file(body.page_path, body.content, f"manual create by {current_user.email}")

    if get_settings().wiki_git_enabled:
        from app.workers.git_push_worker import push_to_remote as _git_push
        _git_push.apply_async(args=[str(workspace_id)], queue="git_push")

    embed_svc = get_embedding_service()
    embedding = await embed_svc.embed_single(body.content)

    page = WikiPage(
        workspace_id=workspace_id,
        page_path=body.page_path,
        title=body.title,
        page_type=body.page_type,
        content_hash=hashlib.sha256(body.content.encode()).hexdigest(),
        git_commit_sha=sha,
        word_count=len(body.content.split()),
        embedding=embedding,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(page)
    await db.flush()

    db.add(WikiPageVersion(
        wiki_page_id=page.id,
        workspace_id=workspace_id,
        git_commit_sha=sha,
        content=body.content,
        change_reason="manual",
        changed_by=current_user.id,
        created_at=datetime.now(UTC).isoformat(),
    ))
    await db.commit()
    await db.refresh(page)
    return WikiPageDetail(**page.__dict__, content=body.content)


@router.get("/pages/{page_path:path}", response_model=WikiPageDetail)
async def get_page(
    workspace_id: uuid.UUID,
    page_path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)
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
    return WikiPageDetail(**page.__dict__, content=content)


@router.put("/pages/{page_path:path}", response_model=WikiPageDetail)
async def update_page(
    workspace_id: uuid.UUID,
    page_path: str,
    body: WikiPageUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.editor)
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
    old_content = repo.read_file(page_path) or ""
    sha = repo.write_file(page_path, body.content, f"manual edit by {current_user.email}")

    if get_settings().wiki_git_enabled:
        from app.workers.git_push_worker import push_to_remote as _git_push
        _git_push.apply_async(args=[str(workspace_id)], queue="git_push")

    diff = repo.compute_diff(old_content, body.content, page_path)

    embed_svc = get_embedding_service()
    new_embedding = await embed_svc.embed_single(body.content)

    drift = _cosine_distance(page.embedding, new_embedding)
    page.content_hash = hashlib.sha256(body.content.encode()).hexdigest()
    page.git_commit_sha = sha
    page.word_count = len(body.content.split())
    page.embedding = new_embedding
    if body.title:
        page.title = body.title
    page.updated_by = current_user.id

    db.add(WikiPageVersion(
        wiki_page_id=page.id,
        workspace_id=workspace_id,
        git_commit_sha=sha,
        content=body.content,
        diff_from_prev=diff,
        semantic_drift_score=drift,
        change_reason="manual",
        changed_by=current_user.id,
        created_at=datetime.now(UTC).isoformat(),
    ))
    await db.commit()
    return WikiPageDetail(**page.__dict__, content=body.content)


@router.get("/pages/{page_path:path}/history")
async def get_page_history(
    workspace_id: uuid.UUID,
    page_path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)
    repo = RepoManager(workspace_id)
    return repo.get_file_history(page_path)


@router.post("/pages/{page_path:path}/rollback")
async def rollback_page(
    workspace_id: uuid.UUID,
    page_path: str,
    body: RollbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.editor)
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
    sha = repo.rollback_file(
        page_path, body.commit_sha,
        f"rollback to {body.commit_sha[:8]} by {current_user.email}"
    )
    new_content = repo.read_file(page_path) or ""

    embed_svc = get_embedding_service()
    new_embedding = await embed_svc.embed_single(new_content)
    page.git_commit_sha = sha
    page.content_hash = hashlib.sha256(new_content.encode()).hexdigest()
    page.embedding = new_embedding
    page.updated_by = current_user.id

    db.add(WikiPageVersion(
        wiki_page_id=page.id,
        workspace_id=workspace_id,
        git_commit_sha=sha,
        content=new_content,
        change_reason=f"rollback:{body.commit_sha[:8]}",
        changed_by=current_user.id,
        created_at=datetime.now(UTC).isoformat(),
    ))
    await db.commit()
    return {"sha": sha, "page_path": page_path}


@router.delete("/pages/{page_path:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(
    workspace_id: uuid.UUID,
    page_path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.editor)
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
    repo.delete_file(page_path, f"delete by {current_user.email}")

    if get_settings().wiki_git_enabled:
        from app.workers.git_push_worker import push_to_remote as _git_push
        _git_push.apply_async(args=[str(workspace_id)], queue="git_push")

    await db.delete(page)
    await db.commit()


def _cosine_distance(a, b) -> float | None:
    if a is None or b is None:
        return None
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return None
    return 1.0 - dot / (na * nb)
