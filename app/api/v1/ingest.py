import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import Role, require_role
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.dependencies import get_current_user
from app.models.ingest_job import IngestJob
from app.models.user import User

router = APIRouter(prefix="/workspaces/{workspace_id}/ingest", tags=["ingest"])


class IngestRequest(BaseModel):
    source_ids: list[uuid.UUID]


class IngestJobResponse(BaseModel):
    id: uuid.UUID
    status: str
    source_ids: list[uuid.UUID] | None
    pages_touched: list[uuid.UUID] | None
    llm_tokens_used: int | None
    llm_cost_usd: float | None
    error_message: str | None
    started_at: str | None
    completed_at: str | None

    model_config = {"from_attributes": True}


@router.post("", response_model=IngestJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_ingest(
    workspace_id: uuid.UUID,
    body: IngestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.editor)

    job = IngestJob(
        workspace_id=workspace_id,
        source_ids=body.source_ids,
        status="queued",
        triggered_by=current_user.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Dispatch to Celery
    from app.workers.ingest_worker import process_ingest_job
    task = process_ingest_job.apply_async(args=[str(job.id)], queue="ingest")
    job.celery_task_id = task.id
    await db.commit()

    return job


@router.get("/{job_id}", response_model=IngestJobResponse)
async def get_ingest_job(
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)
    job = await db.get(IngestJob, job_id)
    if not job or job.workspace_id != workspace_id:
        raise NotFoundError("IngestJob", str(job_id))
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_ingest_job(
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.editor)
    job = await db.get(IngestJob, job_id)
    if not job or job.workspace_id != workspace_id:
        raise NotFoundError("IngestJob", str(job_id))

    if job.status in ("done", "failed"):
        return

    if job.celery_task_id:
        from app.workers.celery_app import celery_app
        celery_app.control.revoke(job.celery_task_id, terminate=True)

    job.status = "cancelled"
    await db.commit()
