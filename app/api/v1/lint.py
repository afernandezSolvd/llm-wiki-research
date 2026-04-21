import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import Role, require_role
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.dependencies import get_current_user
from app.models.lint_run import LintFinding, LintRun
from app.models.user import User

router = APIRouter(prefix="/workspaces/{workspace_id}/lint", tags=["lint"])


class LintRequest(BaseModel):
    scope: str = "full"  # full|page_list
    page_ids: list[uuid.UUID] | None = None


class LintRunResponse(BaseModel):
    id: uuid.UUID
    status: str
    scope: str
    finding_count: int
    auto_fixed: int
    completed_at: str | None

    model_config = {"from_attributes": True}


class LintFindingResponse(BaseModel):
    id: uuid.UUID
    finding_type: str
    severity: str
    description: str
    evidence: dict | None
    auto_fix_applied: bool
    wiki_page_id: uuid.UUID | None

    model_config = {"from_attributes": True}


@router.post("", response_model=LintRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_lint(
    workspace_id: uuid.UUID,
    body: LintRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.editor)

    run = LintRun(
        workspace_id=workspace_id,
        scope=body.scope,
        page_ids_scoped=body.page_ids,
        triggered_by=current_user.id,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    from app.workers.lint_worker import run_lint_pass
    task = run_lint_pass.apply_async(args=[str(run.id)], queue="lint")
    run.celery_task_id = task.id
    await db.commit()

    return run


@router.get("/{run_id}", response_model=LintRunResponse)
async def get_lint_run(
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)
    run = await db.get(LintRun, run_id)
    if not run or run.workspace_id != workspace_id:
        raise NotFoundError("LintRun", str(run_id))
    return run


@router.get("/{run_id}/findings", response_model=list[LintFindingResponse])
async def get_findings(
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    severity: str | None = None,
    finding_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)
    q = select(LintFinding).where(
        LintFinding.lint_run_id == run_id,
        LintFinding.workspace_id == workspace_id,
    )
    if severity:
        q = q.where(LintFinding.severity == severity)
    if finding_type:
        q = q.where(LintFinding.finding_type == finding_type)
    result = await db.execute(q)
    return result.scalars().all()
