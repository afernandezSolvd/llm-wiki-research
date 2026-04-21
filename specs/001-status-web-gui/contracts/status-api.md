# API Contract: Status Endpoints

**Feature**: Status Web GUI (`001-status-web-gui`)
**Base path**: `/api/v1`
**Auth**: JWT Bearer token (existing `get_current_user` dependency)
**Date**: 2026-04-21

---

## GET /api/v1/workspaces/{workspace_id}/status/components

Returns health status of all system components for display in the health panel.

**Auth**: Any workspace member (reader or above).

**Path parameters**:
| Param | Type | Description |
|---|---|---|
| `workspace_id` | UUID | Target workspace |

**Response 200**:
```json
{
  "components": [
    {
      "name": "api",
      "status": "healthy",
      "queue_depth": null,
      "last_seen": null,
      "detail": null
    },
    {
      "name": "ingest_worker",
      "status": "healthy",
      "queue_depth": 3,
      "last_seen": "2026-04-21T10:00:00Z",
      "detail": null
    },
    {
      "name": "lint_worker",
      "status": "unreachable",
      "queue_depth": 0,
      "last_seen": "2026-04-21T09:45:00Z",
      "detail": "No ping response within 2s"
    },
    {
      "name": "embedding_worker",
      "status": "healthy",
      "queue_depth": 0,
      "last_seen": "2026-04-21T10:00:00Z",
      "detail": null
    },
    {
      "name": "graph_worker",
      "status": "healthy",
      "queue_depth": 0,
      "last_seen": "2026-04-21T10:00:00Z",
      "detail": null
    },
    {
      "name": "database",
      "status": "healthy",
      "queue_depth": null,
      "last_seen": null,
      "detail": null
    },
    {
      "name": "broker",
      "status": "healthy",
      "queue_depth": null,
      "last_seen": null,
      "detail": null
    }
  ],
  "generated_at": "2026-04-21T10:00:05Z"
}
```

**Response 401**: Invalid or missing JWT.
**Response 403**: User is not a member of the workspace.
**Response 404**: Workspace not found.

**Implementation notes**:
- Celery `inspect().ping(timeout=2)` is called in a thread executor (non-blocking).
- Queue depth: `redis_client.llen(queue_name)` for each queue.
- Database health: `await db.execute(text("SELECT 1"))`.
- Broker health: `redis_client.ping()`.
- If Celery inspect times out, all workers report `"unreachable"` with
  `detail: "No ping response within 2s"`.

---

## GET /api/v1/workspaces/{workspace_id}/status/jobs

Returns recent background jobs for the workspace (last 24 hours).

**Auth**: Any workspace member (reader or above).

**Path parameters**:
| Param | Type | Description |
|---|---|---|
| `workspace_id` | UUID | Target workspace |

**Query parameters**:
| Param | Type | Default | Description |
|---|---|---|---|
| `status` | string | `null` | Filter by status: `queued`, `running`, `done`, `failed`, `cancelled` |
| `limit` | int | `50` | Max jobs to return (1–100) |

**Response 200**:
```json
{
  "jobs": [
    {
      "id": "a1b2c3d4-...",
      "queue": "ingest",
      "status": "running",
      "source_name": "engineering-handbook.pdf",
      "started_at": "2026-04-21T09:58:00Z",
      "completed_at": null,
      "duration_seconds": null,
      "error_message": null,
      "retry_count": 0
    },
    {
      "id": "e5f6g7h8-...",
      "queue": "ingest",
      "status": "failed",
      "source_name": "corrupted-doc.pdf",
      "started_at": "2026-04-21T09:55:00Z",
      "completed_at": "2026-04-21T09:56:30Z",
      "duration_seconds": 90.0,
      "error_message": "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff",
      "retry_count": 3
    }
  ],
  "total_running": 1,
  "total_queued": 2,
  "total_failed_24h": 1,
  "generated_at": "2026-04-21T10:00:05Z"
}
```

**Response 401/403/404**: Same as above.

**Implementation notes**:
- Queries `IngestJob` and `LintRun` tables for the workspace, `created_at >
  NOW() - INTERVAL '24 hours'`, ordered by `created_at DESC`, limited to
  `limit`.
- `source_name` is derived by joining `IngestJob.source_ids` → `Source.display_name`.
  If multiple sources, use the first one with `+N more` suffix.
- `retry_count` is derived from `celery_task_id` if available, otherwise `0`.
- `error_message` is truncated to 500 characters.

---

## GET /api/v1/workspaces/{workspace_id}/status/quality

Returns semantic drift alerts and the most recent lint run summary.

**Auth**: Any workspace member (reader or above).

**Path parameters**:
| Param | Type | Description |
|---|---|---|
| `workspace_id` | UUID | Target workspace |

**Response 200**:
```json
{
  "drift_alerts": [
    {
      "page_id": "aabbccdd-...",
      "slug": "company-overview",
      "title": "Company Overview",
      "drift_score": 0.42,
      "severity": "warning"
    },
    {
      "page_id": "eeff0011-...",
      "slug": "security-policy",
      "title": "Security Policy",
      "drift_score": 0.78,
      "severity": "error"
    }
  ],
  "lint_summary": {
    "run_id": "11223344-...",
    "status": "done",
    "completed_at": "2026-04-21T08:00:00Z",
    "finding_count": 3,
    "findings": [
      {
        "id": "55667788-...",
        "finding_type": "orphan",
        "severity": "warning",
        "page_title": "Old Product Roadmap",
        "description": "Page has no inbound links and no recent source updates."
      }
    ]
  },
  "generated_at": "2026-04-21T10:00:05Z"
}
```

**When no lint run exists**:
```json
{
  "drift_alerts": [],
  "lint_summary": null,
  "generated_at": "2026-04-21T10:00:05Z"
}
```

**Response 401/403/404**: Same as above.

**Implementation notes**:
- `drift_alerts`: pgvector query `original_embedding <=> embedding > threshold`,
  limit 50, ordered by drift_score DESC.
- `lint_summary.findings`: most recent `LintRun` for workspace, up to 20
  findings ordered by severity (error → warning → info).

---

## GET /api/v1/admin/status

System-wide aggregate status across all workspaces. Platform admin only.

**Auth**: `current_user.is_platform_admin == True`.

**Response 200**:
```json
{
  "workspace_summaries": [
    {
      "workspace_id": "ws-uuid-1",
      "workspace_slug": "engineering",
      "active_jobs": 2,
      "failed_jobs_24h": 0,
      "drift_alert_count": 1,
      "lint_finding_count": 3
    },
    {
      "workspace_id": "ws-uuid-2",
      "workspace_slug": "product",
      "active_jobs": 0,
      "failed_jobs_24h": 1,
      "drift_alert_count": 0,
      "lint_finding_count": 0
    }
  ],
  "generated_at": "2026-04-21T10:00:05Z"
}
```

**Response 401**: Missing/invalid JWT.
**Response 403**: User is not a platform admin.

---

## GET /status

Serves the dashboard HTML page from `app/static/status.html`.

**Auth**: None at the HTTP layer (static file). JWT is checked by the API
calls the page makes via JavaScript.

**Response 200**: `text/html` — the dashboard HTML file.

**Implementation note**: Mounted via FastAPI `StaticFiles` at the `/status`
path prefix, or as a custom route returning `FileResponse("app/static/status.html")`.
