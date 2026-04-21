from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ComponentStatus(BaseModel):
    name: str
    status: Literal["healthy", "degraded", "unreachable"]
    queue_depth: int | None = None
    last_seen: datetime | None = None
    detail: str | None = None


class ComponentsResponse(BaseModel):
    components: list[ComponentStatus]
    generated_at: datetime


class JobSummary(BaseModel):
    id: uuid.UUID
    queue: Literal["ingest", "lint", "embedding", "graph"]
    status: str
    source_name: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    retry_count: int = 0
    progress: str | None = None
    pages_touched: int | None = None


class JobsResponse(BaseModel):
    jobs: list[JobSummary]
    total_running: int
    total_queued: int
    total_failed_24h: int
    generated_at: datetime


class DriftAlert(BaseModel):
    page_id: uuid.UUID
    page_path: str
    title: str
    drift_score: float
    severity: Literal["warning", "error"]


class LintFindingSummary(BaseModel):
    id: uuid.UUID
    finding_type: str
    severity: str
    page_title: str | None = None
    description: str


class LintRunSummary(BaseModel):
    run_id: uuid.UUID
    status: str
    completed_at: str | None = None
    finding_count: int
    findings: list[LintFindingSummary]


class QualityResponse(BaseModel):
    drift_alerts: list[DriftAlert]
    lint_summary: LintRunSummary | None = None
    generated_at: datetime


class WorkspaceStatusSummary(BaseModel):
    workspace_id: uuid.UUID
    workspace_slug: str
    active_jobs: int
    failed_jobs_24h: int
    drift_alert_count: int
    lint_finding_count: int


class AdminStatusResponse(BaseModel):
    workspace_summaries: list[WorkspaceStatusSummary]
    generated_at: datetime
