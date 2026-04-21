"""Platform-admin endpoints: cost reporting, user management."""
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.exceptions import ForbiddenError
from app.dependencies import get_current_user
from app.models.ingest_job import IngestJob
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/cost-report")
async def cost_report(
    workspace_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.is_platform_admin:
        raise ForbiddenError("Platform admin only")

    q = select(
        IngestJob.workspace_id,
        func.sum(IngestJob.llm_tokens_used).label("total_tokens"),
        func.sum(IngestJob.llm_cost_usd).label("total_cost_usd"),
        func.count(IngestJob.id).label("job_count"),
    ).group_by(IngestJob.workspace_id)

    if workspace_id:
        q = q.where(IngestJob.workspace_id == workspace_id)

    result = await db.execute(q)
    rows = result.fetchall()
    return [
        {
            "workspace_id": str(r.workspace_id),
            "total_tokens": r.total_tokens or 0,
            "total_cost_usd": float(r.total_cost_usd or 0),
            "job_count": r.job_count,
        }
        for r in rows
    ]


@router.get("/users")
async def list_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.is_platform_admin:
        raise ForbiddenError("Platform admin only")
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [{"id": str(u.id), "email": u.email, "is_active": u.is_active} for u in users]
