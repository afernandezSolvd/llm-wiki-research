# Data Model: Status Web GUI

**Branch**: `001-status-web-gui` | **Phase**: 1 | **Date**: 2026-04-21

## Overview

This feature introduces **no new database tables or migrations**. All data is
read from existing models: `IngestJob`, `LintRun`, `LintFinding`, `WikiPage`,
and system-level data from Redis and Celery.

New Pydantic response schemas are defined in `app/schemas/status.py`.

---

## Response Schemas (Pydantic)

### ComponentStatus

Represents one system component's health.

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Display name: `"api"`, `"ingest_worker"`, `"lint_worker"`, `"embedding_worker"`, `"graph_worker"`, `"database"`, `"broker"` |
| `status` | `Literal["healthy", "degraded", "unreachable"]` | Current health state |
| `queue_depth` | `int \| None` | Pending task count (worker queues only) |
| `last_seen` | `datetime \| None` | Last successful ping (workers only) |
| `detail` | `str \| None` | Human-readable note on degradation cause |

**Derivation rules**:
- API: always `healthy` if the endpoint itself is responding
- Workers: `healthy` if `inspect().ping()` returns a response within timeout;
  `unreachable` otherwise
- Database: `healthy` if a lightweight `SELECT 1` succeeds; `unreachable` on
  exception
- Broker: `healthy` if `redis_client.ping()` succeeds; `unreachable` on exception
- `queue_depth`: populated by `redis_client.llen(queue_name)` for worker entries

---

### JobSummary

A compact view of one background job shown in the jobs panel.

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Job identifier |
| `queue` | `Literal["ingest", "lint", "embedding", "graph"]` | Which queue handled it |
| `status` | `Literal["queued", "running", "done", "failed", "cancelled"]` | Current status |
| `source_name` | `str \| None` | Display name of the source document (ingest only) |
| `started_at` | `datetime \| None` | When the worker picked it up |
| `completed_at` | `datetime \| None` | When it finished (success or failure) |
| `duration_seconds` | `float \| None` | Derived: `(completed_at - started_at).total_seconds()` if both present |
| `error_message` | `str \| None` | First 500 chars of error_message from the job record |
| `retry_count` | `int` | Number of retries consumed (0 if first attempt succeeded) |

**Source**: `IngestJob` and `LintRun` tables. Jobs from the last 24 hours,
ordered by `created_at DESC`, limited to 50 per workspace.

---

### DriftAlert

A wiki page that has exceeded the configured drift threshold.

| Field | Type | Description |
|---|---|---|
| `page_id` | `UUID` | Wiki page identifier |
| `slug` | `str` | URL-friendly page identifier |
| `title` | `str` | Human-readable page title |
| `drift_score` | `float` | Cosine distance between `original_embedding` and `embedding` |
| `severity` | `Literal["warning", "error"]` | `error` if `drift_score > threshold * 2`, else `warning` |

**Source**: `wiki_pages` table via pgvector `<=>` operator.
Threshold from `settings.DRIFT_ALERT_THRESHOLD` (default `0.35`).

---

### LintFindingSummary

One finding from the most recent lint run.

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Finding identifier |
| `finding_type` | `str` | E.g., `"orphan"`, `"contradiction"`, `"stale"` |
| `severity` | `Literal["error", "warning", "info"]` | Finding severity |
| `page_title` | `str \| None` | Title of the affected wiki page |
| `description` | `str` | Short description of the issue |

---

### LintRunSummary

Summary of the most recent lint run for the workspace.

| Field | Type | Description |
|---|---|---|
| `run_id` | `UUID` | Lint run identifier |
| `status` | `str` | Run status (`done`, `failed`, etc.) |
| `completed_at` | `datetime \| None` | When the run finished |
| `finding_count` | `int` | Total findings from this run |
| `findings` | `list[LintFindingSummary]` | Up to 20 most severe findings |

**Source**: Most recent `LintRun` + its `LintFinding` records.

---

### ComponentsResponse

Response for `GET /status/components`.

| Field | Type |
|---|---|
| `components` | `list[ComponentStatus]` |
| `generated_at` | `datetime` |

---

### JobsResponse

Response for `GET /status/jobs`.

| Field | Type |
|---|---|
| `jobs` | `list[JobSummary]` |
| `total_running` | `int` |
| `total_queued` | `int` |
| `total_failed_24h` | `int` |
| `generated_at` | `datetime` |

---

### QualityResponse

Response for `GET /status/quality`.

| Field | Type |
|---|---|
| `drift_alerts` | `list[DriftAlert]` |
| `lint_summary` | `LintRunSummary \| None` |
| `generated_at` | `datetime` |

---

### AdminStatusResponse

Response for `GET /admin/status` (platform admin only).

| Field | Type |
|---|---|
| `workspace_summaries` | `list[WorkspaceStatusSummary]` |
| `generated_at` | `datetime` |

### WorkspaceStatusSummary

| Field | Type |
|---|---|
| `workspace_id` | `UUID` |
| `workspace_slug` | `str` |
| `active_jobs` | `int` |
| `failed_jobs_24h` | `int` |
| `drift_alert_count` | `int` |
| `lint_finding_count` | `int` |

---

## Existing Models Used (Read-Only)

| Model | File | Fields read |
|---|---|---|
| `IngestJob` | `app/models/ingest_job.py` | `id`, `workspace_id`, `status`, `celery_task_id`, `error_message`, `started_at`, `completed_at`, `created_at`, `source_ids` |
| `LintRun` | `app/models/lint_run.py` | `id`, `workspace_id`, `status`, `finding_count`, `completed_at`, `created_at` |
| `LintFinding` | `app/models/lint_run.py` | `id`, `lint_run_id`, `wiki_page_id`, `finding_type`, `severity`, `description` |
| `WikiPage` | `app/models/wiki_page.py` | `id`, `workspace_id`, `slug`, `title`, `embedding`, `original_embedding` |
| `Source` | `app/models/source.py` | `id`, `display_name` (joined from IngestJob.source_ids) |
