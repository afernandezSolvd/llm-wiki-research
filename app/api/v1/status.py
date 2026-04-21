"""Read-only system status endpoints for the dashboard at /status."""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import create_access_token
from app.auth.rbac import Role, require_role
from app.config import get_settings
from app.core.db import get_db
from app.core.exceptions import ForbiddenError
from app.core.logging import get_logger
from app.core.redis import get_redis_pool
from app.dependencies import get_current_user
from app.models.ingest_job import IngestJob
from app.models.lint_run import LintFinding, LintRun
from app.models.user import User
from app.models.wiki_page import WikiPage
from app.models.workspace import Workspace
from app.schemas.status import (
    AdminStatusResponse,
    ComponentStatus,
    ComponentsResponse,
    DriftAlert,
    JobSummary,
    JobsResponse,
    LintFindingSummary,
    LintRunSummary,
    QualityResponse,
    WorkspaceStatusSummary,
)

router = APIRouter(tags=["status"])
logger = get_logger(__name__)

_WORKER_QUEUES = ("ingest", "lint", "embedding", "graph")
_STATUS_SERVICE_EMAIL = "status-reader@internal"


# ─── Bootstrap response schema ────────────────────────────────────────────────

class WorkspaceItem(BaseModel):
    id: uuid.UUID
    slug: str
    display_name: str


class BootstrapResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    workspaces: list[WorkspaceItem]


# ─── Bootstrap endpoint (public — no auth required) ───────────────────────────

@router.get("/status/bootstrap", response_model=BootstrapResponse)
async def bootstrap(db: AsyncSession = Depends(get_db)) -> BootstrapResponse:
    """Return a server-issued read-only JWT and workspace list. No credentials needed."""
    logger.info("status.bootstrap.request")

    # Find or create the internal status-reader service account
    result = await db.execute(select(User).where(User.email == _STATUS_SERVICE_EMAIL))
    service_user = result.scalar_one_or_none()

    if service_user is None:
        hashed = bcrypt.hashpw(uuid.uuid4().bytes, bcrypt.gensalt()).decode()
        service_user = User(
            email=_STATUS_SERVICE_EMAIL,
            hashed_password=hashed,
            full_name="Status Reader (service account)",
            is_active=True,
            is_platform_admin=True,
        )
        db.add(service_user)
        await db.commit()
        await db.refresh(service_user)
        logger.info("status.bootstrap.service_account_created", user_id=str(service_user.id))

    token = create_access_token(service_user.id)

    workspaces = (await db.execute(
        select(Workspace).where(Workspace.deleted_at.is_(None)).order_by(Workspace.created_at)
    )).scalars().all()

    ws_list = [WorkspaceItem(id=ws.id, slug=ws.slug, display_name=ws.display_name) for ws in workspaces]

    logger.info("status.bootstrap.response", workspace_count=len(ws_list))
    return BootstrapResponse(access_token=token, workspaces=ws_list)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(UTC)


def _celery_active_queues() -> dict[str, Any] | None:
    """Return {worker_name: [{name: queue_name, ...}]} or None if unreachable."""
    from app.workers.celery_app import celery_app
    try:
        return celery_app.control.inspect(timeout=2).active_queues()
    except Exception:
        return None


async def _check_components(db: AsyncSession) -> list[ComponentStatus]:
    redis = get_redis_pool()
    components: list[ComponentStatus] = []

    # API is always healthy if we reach this code
    components.append(ComponentStatus(name="api", status="healthy"))

    # Workers via Celery inspect (blocking → thread executor)
    loop = asyncio.get_running_loop()
    queues_result = await loop.run_in_executor(None, _celery_active_queues)

    # queues_result maps worker_name → list of {name, exchange, routing_key, ...}
    active_queue_names: set[str] = set()
    if queues_result:
        for worker_queues in queues_result.values():
            for q in worker_queues:
                if isinstance(q, dict) and q.get("name"):
                    active_queue_names.add(q["name"].lower())

    for queue in _WORKER_QUEUES:
        # Check queue depth
        try:
            depth = await redis.llen(queue)
        except Exception:
            depth = None

        is_up = queue in active_queue_names
        if is_up:
            detail = None
        elif queues_result is not None:
            detail = "No active workers consuming this queue"
        else:
            detail = "No response within 2s"
        components.append(ComponentStatus(
            name=f"{queue}_worker",
            status="healthy" if is_up else "unreachable",
            queue_depth=depth,
            detail=detail,
        ))

    # Database
    try:
        await db.execute(text("SELECT 1"))
        components.append(ComponentStatus(name="database", status="healthy"))
    except Exception as exc:
        components.append(ComponentStatus(name="database", status="unreachable", detail=str(exc)[:120]))

    # Broker (Redis)
    try:
        await redis.ping()
        components.append(ComponentStatus(name="broker", status="healthy"))
    except Exception as exc:
        components.append(ComponentStatus(name="broker", status="unreachable", detail=str(exc)[:120]))

    return components


# ─── US1: System Health ───────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/status/components", response_model=ComponentsResponse)
async def get_components(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ComponentsResponse:
    logger.info("status.components.request", workspace_id=str(workspace_id), user_id=str(current_user.id))
    await require_role(db, current_user, workspace_id, Role.reader)

    components = await _check_components(db)

    logger.info("status.components.response", workspace_id=str(workspace_id), component_count=len(components))
    return ComponentsResponse(components=components, generated_at=_now_utc())


# ─── US2: Job Monitoring ──────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/status/jobs", response_model=JobsResponse)
async def get_jobs(
    workspace_id: uuid.UUID,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobsResponse:
    logger.info("status.jobs.request", workspace_id=str(workspace_id), user_id=str(current_user.id))
    await require_role(db, current_user, workspace_id, Role.reader)

    cutoff = _now_utc() - timedelta(hours=24)

    # Ingest jobs
    ingest_q = (
        select(IngestJob)
        .where(IngestJob.workspace_id == workspace_id, IngestJob.created_at >= cutoff)
        .order_by(IngestJob.created_at.desc())
        .limit(limit)
    )
    if status:
        ingest_q = ingest_q.where(IngestJob.status == status)
    ingest_rows = (await db.execute(ingest_q)).scalars().all()

    # Lint runs (counts as jobs too)
    lint_q = (
        select(LintRun)
        .where(LintRun.workspace_id == workspace_id, LintRun.created_at >= cutoff)
        .order_by(LintRun.created_at.desc())
        .limit(limit)
    )
    if status:
        lint_q = lint_q.where(LintRun.status == status)
    lint_rows = (await db.execute(lint_q)).scalars().all()

    redis = get_redis_pool()
    jobs: list[JobSummary] = []

    for j in ingest_rows:
        dur = None
        if j.started_at and j.completed_at:
            try:
                s = datetime.fromisoformat(j.started_at)
                e = datetime.fromisoformat(j.completed_at)
                # Strip tzinfo if one side is naive to avoid TypeError
                if (s.tzinfo is None) != (e.tzinfo is None):
                    s = s.replace(tzinfo=None)
                    e = e.replace(tzinfo=None)
                computed = (e - s).total_seconds()
                if computed >= 0:
                    dur = computed
            except (ValueError, TypeError):
                pass

        # Source name from first source_id (best-effort; no join to keep it fast)
        source_name: str | None = None
        if j.source_ids:
            extra = len(j.source_ids) - 1
            source_name = str(j.source_ids[0])[:8] + "…"
            if extra > 0:
                source_name += f" +{extra} more"

        # For running jobs, read live stage from Redis
        progress: str | None = None
        if j.status == "running":
            try:
                progress = await redis.get(f"ingest:progress:{j.id}")
            except Exception:
                pass

        jobs.append(JobSummary(
            id=j.id,
            queue="ingest",
            status=j.status,
            source_name=source_name,
            started_at=j.started_at,
            completed_at=j.completed_at,
            duration_seconds=dur,
            error_message=(j.error_message or "")[:500] or None,
            retry_count=0,
            progress=progress,
            pages_touched=len(j.pages_touched) if j.pages_touched else None,
        ))

    for r in lint_rows:
        jobs.append(JobSummary(
            id=r.id,
            queue="lint",
            status=r.status,
            started_at=None,
            completed_at=r.completed_at,
            error_message=None,
            retry_count=0,
        ))

    # Sort combined list newest-first
    jobs.sort(key=lambda j: j.started_at or "", reverse=True)

    # Aggregate counts (across all 24h, not just the limited list)
    total_running = (await db.execute(
        select(func.count()).where(
            IngestJob.workspace_id == workspace_id,
            IngestJob.status == "running",
            IngestJob.created_at >= cutoff,
        )
    )).scalar_one()

    total_queued = (await db.execute(
        select(func.count()).where(
            IngestJob.workspace_id == workspace_id,
            IngestJob.status == "queued",
            IngestJob.created_at >= cutoff,
        )
    )).scalar_one()

    total_failed = (await db.execute(
        select(func.count()).where(
            IngestJob.workspace_id == workspace_id,
            IngestJob.status == "failed",
            IngestJob.created_at >= cutoff,
        )
    )).scalar_one()

    logger.info("status.jobs.response", workspace_id=str(workspace_id), job_count=len(jobs))
    return JobsResponse(
        jobs=jobs[:limit],
        total_running=total_running,
        total_queued=total_queued,
        total_failed_24h=total_failed,
        generated_at=_now_utc(),
    )


# ─── US3: Knowledge Quality ───────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/status/quality", response_model=QualityResponse)
async def get_quality(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QualityResponse:
    logger.info("status.quality.request", workspace_id=str(workspace_id), user_id=str(current_user.id))
    await require_role(db, current_user, workspace_id, Role.reader)

    settings = get_settings()
    threshold = settings.drift_alert_threshold

    # Drift alerts via pgvector cosine distance
    drift_alerts: list[DriftAlert] = []
    try:
        drift_q = await db.execute(
            text("""
                SELECT id, page_path, title,
                       (original_embedding <=> embedding) AS drift_score
                FROM wiki_pages
                WHERE workspace_id = :ws_id
                  AND original_embedding IS NOT NULL
                  AND embedding IS NOT NULL
                  AND (original_embedding <=> embedding) > :threshold
                ORDER BY drift_score DESC
                LIMIT 50
            """),
            {"ws_id": workspace_id, "threshold": threshold},
        )
        for row in drift_q.fetchall():
            severity = "error" if row.drift_score > threshold * 2 else "warning"
            drift_alerts.append(DriftAlert(
                page_id=row.id,
                page_path=row.page_path,
                title=row.title,
                drift_score=round(float(row.drift_score), 4),
                severity=severity,
            ))
    except Exception as exc:
        logger.warning("status.quality.drift_query_failed", error=str(exc))

    # Most recent lint run + findings
    lint_summary: LintRunSummary | None = None
    try:
        latest_run = (await db.execute(
            select(LintRun)
            .where(LintRun.workspace_id == workspace_id)
            .order_by(LintRun.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        if latest_run:
            findings_q = await db.execute(
                select(LintFinding, WikiPage.title)
                .outerjoin(WikiPage, LintFinding.wiki_page_id == WikiPage.id)
                .where(LintFinding.lint_run_id == latest_run.id)
                .order_by(
                    case(
                        (LintFinding.severity == "error", 0),
                        (LintFinding.severity == "warning", 1),
                        else_=2,
                    )
                )
                .limit(20)
            )
            finding_summaries = [
                LintFindingSummary(
                    id=f.id,
                    finding_type=f.finding_type,
                    severity=f.severity,
                    page_title=page_title,
                    description=f.description,
                )
                for f, page_title in findings_q.fetchall()
            ]
            lint_summary = LintRunSummary(
                run_id=latest_run.id,
                status=latest_run.status,
                completed_at=latest_run.completed_at,
                finding_count=latest_run.finding_count,
                findings=finding_summaries,
            )
    except Exception as exc:
        logger.warning("status.quality.lint_query_failed", error=str(exc))

    logger.info(
        "status.quality.response",
        workspace_id=str(workspace_id),
        drift_count=len(drift_alerts),
        has_lint=lint_summary is not None,
    )
    return QualityResponse(
        drift_alerts=drift_alerts,
        lint_summary=lint_summary,
        generated_at=_now_utc(),
    )


# ─── US3: Admin aggregate (platform_admin only) ───────────────────────────────

@router.get("/admin/status", response_model=AdminStatusResponse)
async def get_admin_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdminStatusResponse:
    logger.info("status.admin.request", user_id=str(current_user.id))
    if not current_user.is_platform_admin:
        raise ForbiddenError("Platform admin only")

    settings = get_settings()
    threshold = settings.drift_alert_threshold
    cutoff = _now_utc() - timedelta(hours=24)

    workspaces = (await db.execute(
        select(Workspace).where(Workspace.deleted_at.is_(None))
    )).scalars().all()

    summaries: list[WorkspaceStatusSummary] = []
    for ws in workspaces:
        active_jobs = (await db.execute(
            select(func.count(IngestJob.id)).where(
                IngestJob.workspace_id == ws.id,
                IngestJob.status.in_(["queued", "running"]),
            )
        )).scalar_one()

        failed_jobs = (await db.execute(
            select(func.count(IngestJob.id)).where(
                IngestJob.workspace_id == ws.id,
                IngestJob.status == "failed",
                IngestJob.created_at >= cutoff,
            )
        )).scalar_one()

        drift_count = 0
        try:
            result = await db.execute(
                text("""
                    SELECT COUNT(*) FROM wiki_pages
                    WHERE workspace_id = :ws_id
                      AND original_embedding IS NOT NULL
                      AND embedding IS NOT NULL
                      AND (original_embedding <=> embedding) > :threshold
                """),
                {"ws_id": ws.id, "threshold": threshold},
            )
            drift_count = result.scalar_one()
        except Exception:
            pass

        lint_finding_count = 0
        try:
            latest_run = (await db.execute(
                select(LintRun.finding_count)
                .where(LintRun.workspace_id == ws.id)
                .order_by(LintRun.created_at.desc())
                .limit(1)
            )).scalar_one_or_none()
            if latest_run is not None:
                lint_finding_count = latest_run
        except Exception:
            pass

        summaries.append(WorkspaceStatusSummary(
            workspace_id=ws.id,
            workspace_slug=ws.slug,
            active_jobs=active_jobs,
            failed_jobs_24h=failed_jobs,
            drift_alert_count=drift_count,
            lint_finding_count=lint_finding_count,
        ))

    logger.info("status.admin.response", workspace_count=len(summaries))
    return AdminStatusResponse(workspace_summaries=summaries, generated_at=_now_utc())
