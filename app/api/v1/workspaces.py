import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import Role, require_role
from app.config import get_settings
from app.core.db import get_db
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.dependencies import get_current_user, get_workspace
from app.git.repo_manager import RepoManager
from app.models.schema_config import SchemaConfig
from app.models.user import User, UserWorkspaceMembership
from app.models.workspace import Workspace

logger = get_logger(__name__)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class WorkspaceCreate(BaseModel):
    slug: str
    display_name: str


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    slug: str
    display_name: str
    schema_version: int

    model_config = {"from_attributes": True}


class WorkspaceCloneUrlResponse(BaseModel):
    clone_url: str
    workspace_slug: str
    last_push_at: datetime | None
    setup: dict


class MemberAdd(BaseModel):
    user_id: uuid.UUID
    role: str  # admin|editor|reader


class MemberUpdate(BaseModel):
    role: str


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.is_platform_admin:
        result = await db.execute(
            select(Workspace).where(Workspace.deleted_at.is_(None))
        )
    else:
        result = await db.execute(
            select(Workspace)
            .join(UserWorkspaceMembership, UserWorkspaceMembership.workspace_id == Workspace.id)
            .where(
                UserWorkspaceMembership.user_id == current_user.id,
                Workspace.deleted_at.is_(None),
            )
        )
    return result.scalars().all()


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.is_platform_admin:
        raise ForbiddenError("Only platform admins can create workspaces")

    existing = await db.execute(select(Workspace).where(Workspace.slug == body.slug))
    if existing.scalar_one_or_none():
        raise ConflictError(f"Workspace slug '{body.slug}' already taken")

    ws = Workspace(
        slug=body.slug,
        display_name=body.display_name,
        git_repo_path=f"wiki_repos/{uuid.uuid4()}",  # placeholder
    )
    db.add(ws)
    await db.flush()

    # Initialize git repo
    repo = RepoManager(ws.id)
    ws.git_repo_path = str(repo.repo_path)
    repo.init()

    # Create default schema config
    from app.git.repo_manager import DEFAULT_SCHEMA
    schema = SchemaConfig(
        workspace_id=ws.id,
        content=DEFAULT_SCHEMA,
        updated_by=current_user.id,
    )
    db.add(schema)

    # Auto-provision remote git repo if enabled
    settings = get_settings()
    if settings.wiki_git_enabled:
        try:
            from app.git.providers import get_provider
            provider = get_provider(settings)
            clone_url = provider.create_repo(settings.wiki_git_org, f"wiki-{ws.slug}")
            repo.set_remote(clone_url)
            ws.git_remote_url = clone_url
        except Exception as exc:
            logger.warning("git_remote_provision_error", workspace_id=str(ws.id), error=str(exc))

    # Add creator as admin
    db.add(UserWorkspaceMembership(
        user_id=current_user.id,
        workspace_id=ws.id,
        role="admin",
        invited_by=current_user.id,
    ))

    await db.commit()
    await db.refresh(ws)
    return ws


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace_detail(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)
    ws = await get_workspace(workspace_id, db)
    return ws


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.admin)
    ws = await db.get(Workspace, workspace_id)
    if not ws:
        raise NotFoundError("Workspace", str(workspace_id))
    ws.deleted_at = datetime.now(UTC)
    await db.commit()


@router.post("/{workspace_id}/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    workspace_id: uuid.UUID,
    body: MemberAdd,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.admin)
    target_user = await db.get(User, body.user_id)
    if not target_user:
        raise NotFoundError("User", str(body.user_id))

    existing = await db.execute(
        select(UserWorkspaceMembership).where(
            UserWorkspaceMembership.user_id == body.user_id,
            UserWorkspaceMembership.workspace_id == workspace_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError("User is already a member")

    db.add(UserWorkspaceMembership(
        user_id=body.user_id,
        workspace_id=workspace_id,
        role=body.role,
        invited_by=current_user.id,
    ))
    await db.commit()
    return {"status": "added"}


@router.patch("/{workspace_id}/members/{user_id}")
async def update_member_role(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    body: MemberUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.admin)
    result = await db.execute(
        select(UserWorkspaceMembership).where(
            UserWorkspaceMembership.user_id == user_id,
            UserWorkspaceMembership.workspace_id == workspace_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise NotFoundError("Membership", str(user_id))
    membership.role = body.role
    await db.commit()
    return {"status": "updated"}


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.admin)
    result = await db.execute(
        select(UserWorkspaceMembership).where(
            UserWorkspaceMembership.user_id == user_id,
            UserWorkspaceMembership.workspace_id == workspace_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise NotFoundError("Membership", str(user_id))
    await db.delete(membership)
    await db.commit()


@router.get("/{workspace_id}/clone-url", response_model=WorkspaceCloneUrlResponse)
async def get_clone_url(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)
    ws = await get_workspace(workspace_id, db)

    if ws.git_remote_url is None:
        raise ConflictError(
            "Remote sync is not configured for this workspace. "
            "Contact your administrator to enable git remote push."
        )

    return WorkspaceCloneUrlResponse(
        clone_url=ws.git_remote_url,
        workspace_slug=ws.slug,
        last_push_at=ws.git_last_push_at,
        setup={
            "clone_command": f"git clone {ws.git_remote_url} ~/{ws.slug}",
            "obsidian_note": (
                "Open the cloned folder as an Obsidian vault. "
                "Install the 'Obsidian Git' community plugin and set auto-pull interval "
                "to 60 seconds for live updates."
            ),
            "plugin_url": "https://github.com/denolehov/obsidian-git",
        },
    )
