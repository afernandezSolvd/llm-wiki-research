import uuid
from enum import IntEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.models.user import User, UserWorkspaceMembership


class Role(IntEnum):
    reader = 1
    editor = 2
    admin = 3

    @classmethod
    def from_str(cls, s: str) -> "Role":
        return cls[s]


async def get_membership(
    db: AsyncSession,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> UserWorkspaceMembership | None:
    result = await db.execute(
        select(UserWorkspaceMembership).where(
            UserWorkspaceMembership.user_id == user_id,
            UserWorkspaceMembership.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


async def require_role(
    db: AsyncSession,
    user: User,
    workspace_id: uuid.UUID,
    min_role: Role,
) -> UserWorkspaceMembership:
    if user.is_platform_admin:
        # Platform admins bypass workspace RBAC
        membership = await get_membership(db, user.id, workspace_id)
        if membership is None:
            # Synthesize an admin membership for platform admins
            membership = UserWorkspaceMembership(
                user_id=user.id,
                workspace_id=workspace_id,
                role="admin",
            )
        return membership

    membership = await get_membership(db, user.id, workspace_id)
    if membership is None:
        raise ForbiddenError("Not a member of this workspace")

    if Role.from_str(membership.role) < min_role:
        raise ForbiddenError(f"Requires {min_role.name} role or higher")

    return membership
