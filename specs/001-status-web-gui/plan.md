# Implementation Plan: Status Web GUI

**Branch**: `001-status-web-gui` | **Date**: 2026-04-21 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-status-web-gui/spec.md`

## Summary

Add a read-only status dashboard accessible at `/status` in the existing
FastAPI application. The dashboard exposes three real-time panels — system
component health, background job monitoring, and knowledge quality metrics —
auto-refreshing every 20 seconds. Backed by four new GET-only API endpoints
that query existing database models (IngestJob, LintRun, LintFinding,
WikiPage) plus Celery inspect and Redis LLEN for live worker/queue data.
Frontend is a single HTML file with HTMX (CDN) served as a static file from
the running FastAPI process — no build pipeline, no separate deployment.

## Technical Context

**Language/Version**: Python 3.12 (backend, existing), HTML5/ES2022 (frontend,
no transpilation)
**Primary Dependencies**: FastAPI + SQLAlchemy 2.0 async (existing), Celery 5
inspect API (existing), Redis 7 via `get_redis_pool()` (existing), HTMX 2.x
via CDN (new frontend dep, no install)
**Storage**: PostgreSQL 16 via existing models; Redis 7 for queue depth (LLEN)
**Testing**: pytest + pytest-asyncio (existing), `httpx.AsyncClient` for
endpoint tests
**Target Platform**: Browser (desktop/laptop 1280×800+), served from FastAPI
process on port 8000
**Project Type**: web-service extension — new read-only API routes + static
HTML page
**Performance Goals**: `/status/components` p95 ≤ 2500ms (Celery inspect
timeout-bound); `/status/jobs` and `/status/quality` p95 ≤ 300ms; dashboard
data staleness ≤ 30s
**Constraints**: Read-only (zero state mutations), JWT auth reused, workspace-
scoped, no separate deployment, no build pipeline
**Scale/Scope**: Same scale as existing API; 1 dashboard page, 4 new
endpoints, ~3 new source files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. LLM Wiki Pattern | Dashboard reads existing wiki data; no new ingest/query/lint flows touched | ✅ PASS |
| II. Multi-Tenant Workspace Isolation | All endpoints scoped to `workspace_id` with existing membership dependency; platform_admin gate for cross-workspace view | ✅ PASS |
| III. Async Worker Architecture | No new Celery workers; new FastAPI endpoints are async; Celery inspect called via `run_in_executor` to avoid blocking event loop | ✅ PASS |
| IV. Knowledge Quality Controls | Dashboard exposes existing drift scores and lint findings; does not write to wiki_pages or embeddings | ✅ PASS |
| V. Observability & Structured Logging | New endpoints emit structured key=value logs; feature's purpose is to increase worker health visibility | ✅ PASS |
| VI. Test Discipline | New router gets unit tests (mocked DB/Redis/Celery) in `tests/unit/test_status.py`; integration tests in `tests/integration/test_status_api.py` against real DB | ✅ PASS |

**Post-design re-check**: All six principles pass. No complexity justification required.

## Project Structure

### Documentation (this feature)

```text
specs/001-status-web-gui/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── status-api.md    # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks — not created here)
```

### Source Code (repository root)

```text
app/
├── api/
│   └── v1/
│       └── status.py            # New: status aggregation router (4 endpoints)
├── schemas/
│   └── status.py                # New: Pydantic response schemas
├── static/
│   └── status.html              # New: dashboard HTML (HTMX, vanilla JS)
└── main.py                      # Modified: mount StaticFiles, include status router

tests/
├── unit/
│   └── test_status.py           # New: unit tests (mocked boundaries)
└── integration/
    └── test_status_api.py       # New: integration tests (real DB)
```

**Structure Decision**: Single-project extension. All new code lives under
`app/` alongside existing modules. The frontend is one static HTML file;
no `frontend/` directory or build toolchain is needed.

## Phase 0: Research Output

**All NEEDS CLARIFICATION items resolved.** See [research.md](research.md)
for full decision log. Key decisions:

1. **Frontend**: Static HTML + HTMX via CDN, served from FastAPI `StaticFiles`
   at `/status` — no build step, no separate deployment.
2. **Worker health**: `celery_app.control.inspect(timeout=2).ping()` wrapped
   in `asyncio.get_running_loop().run_in_executor()`.
3. **Queue depth**: `redis_client.llen(queue_name)` for each of the 4 queues.
4. **Drift data**: pgvector `original_embedding <=> embedding > threshold`
   query on `wiki_pages` table.
5. **Lint summary**: Most recent `LintRun` + up to 20 `LintFinding` records.
6. **Endpoints**: Four separate GET endpoints per panel (components, jobs,
   quality, admin aggregate) to enable independent HTMX partial refresh.
7. **Auth**: Reuse existing `get_current_user` + workspace membership
   dependency — no new auth code.

## Phase 1: Design Output

### Data Model

No new database tables or migrations. New Pydantic schemas only.
See [data-model.md](data-model.md) for full schema definitions.

**New schemas in `app/schemas/status.py`**:
- `ComponentStatus` — one system component with health/depth/last_seen
- `JobSummary` — compact job row for the jobs panel
- `DriftAlert` — wiki page with drift_score and severity
- `LintFindingSummary` + `LintRunSummary` — latest lint run + top findings
- `ComponentsResponse`, `JobsResponse`, `QualityResponse` — panel responses
- `AdminStatusResponse` + `WorkspaceStatusSummary` — admin aggregate

### API Contracts

See [contracts/status-api.md](contracts/status-api.md).

Four new GET-only endpoints:

| Endpoint | Panel | Auth |
|---|---|---|
| `GET /api/v1/workspaces/{ws}/status/components` | Health panel | workspace member |
| `GET /api/v1/workspaces/{ws}/status/jobs` | Jobs panel | workspace member |
| `GET /api/v1/workspaces/{ws}/status/quality` | Quality panel | workspace member |
| `GET /api/v1/admin/status` | Admin aggregate | platform_admin only |

Static page served at `GET /status` (FastAPI `FileResponse` or `StaticFiles`).

### Quickstart

See [quickstart.md](quickstart.md) — includes curl validation steps and
troubleshooting guide.

### Agent Context

Updated by `.specify/scripts/bash/update-agent-context.sh claude`.

## Complexity Tracking

> No constitution violations. No justifications required.
