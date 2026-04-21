"""FastAPI dependency injection factories."""
import uuid

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_token
from app.core.db import get_db
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.user import User
from app.models.workspace import Workspace

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    user_id = decode_token(credentials.credentials)
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise ForbiddenError("User not found or inactive")
    return user


async def get_workspace(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Workspace:
    ws = await db.get(Workspace, workspace_id)
    if not ws or ws.deleted_at is not None:
        raise NotFoundError("Workspace", str(workspace_id))
    return ws
