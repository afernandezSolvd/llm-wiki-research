import hashlib
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import Role, require_role
from app.core.db import get_db
from app.dependencies import get_current_user
from app.git.repo_manager import RepoManager
from app.models.schema_config import SchemaConfig
from app.models.user import User

router = APIRouter(prefix="/workspaces/{workspace_id}/schema", tags=["schema"])


class SchemaResponse(BaseModel):
    version: int
    content: str
    content_hash: str | None


class SchemaUpdate(BaseModel):
    content: str


@router.get("", response_model=SchemaResponse)
async def get_schema(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)
    result = await db.execute(
        select(SchemaConfig).where(SchemaConfig.workspace_id == workspace_id)
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        return SchemaResponse(version=0, content="", content_hash=None)
    return SchemaResponse(version=cfg.version, content=cfg.content, content_hash=cfg.content_hash)


@router.put("", response_model=SchemaResponse)
async def update_schema(
    workspace_id: uuid.UUID,
    body: SchemaUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.admin)
    result = await db.execute(
        select(SchemaConfig).where(SchemaConfig.workspace_id == workspace_id)
    )
    cfg = result.scalar_one_or_none()
    content_hash = hashlib.sha256(body.content.encode()).hexdigest()

    if cfg:
        cfg.content = body.content
        cfg.content_hash = content_hash
        cfg.version += 1
        cfg.updated_by = current_user.id
    else:
        cfg = SchemaConfig(
            workspace_id=workspace_id,
            content=body.content,
            content_hash=content_hash,
            version=1,
            updated_by=current_user.id,
        )
        db.add(cfg)

    # Write to git repo
    repo = RepoManager(workspace_id)
    repo.write_file("schema.md", body.content, f"schema update by {current_user.email}")

    # Invalidate prompt cache
    from app.core.redis import get_redis_pool
    redis = get_redis_pool()
    await redis.delete(f"prompt_cache:schema:{workspace_id}")

    await db.commit()
    return SchemaResponse(version=cfg.version, content=cfg.content, content_hash=cfg.content_hash)
