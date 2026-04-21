---

description: "Task list for Status Web GUI feature implementation"
---

# Tasks: Status Web GUI

**Input**: Design documents from `/specs/001-status-web-gui/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Organization**: Tasks are grouped by user story to enable independent
implementation and testing of each story.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths included in all descriptions

## Path Conventions

Single-project extension of existing FastAPI backend. New files:
- `app/api/v1/status.py` — status router
- `app/schemas/status.py` — Pydantic response schemas
- `app/static/status.html` — dashboard HTML

---

## Phase 1: Setup

**Purpose**: Wire new files into the existing application so all user story
phases can start.

- [x] T001 Modify `app/main.py` to add `GET /status` route returning
  `FileResponse("app/static/status.html")`, include the status router from
  `app/api/v1/status.py` under prefix `/api/v1/workspaces/{workspace_id}/status`,
  and create stub files `app/api/v1/status.py` (empty `APIRouter`) and
  `app/static/status.html` (empty HTML document)

**Checkpoint**: `make dev` starts without import errors; `curl localhost:8000/status`
returns 200; `curl localhost:8000/api/v1/workspaces/any/status/components`
returns 404 (router exists, no routes yet)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared schemas and HTML shell required by all three user stories.

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete.

- [x] T002 [P] Create `app/schemas/status.py` with all Pydantic response schemas
  from `specs/001-status-web-gui/data-model.md`: `ComponentStatus`,
  `ComponentsResponse`, `JobSummary`, `JobsResponse`, `DriftAlert`,
  `LintFindingSummary`, `LintRunSummary`, `QualityResponse`,
  `WorkspaceStatusSummary`, `AdminStatusResponse` — include `generated_at:
  datetime` field on each response model

- [x] T003 [P] Add HTML shell to `app/static/status.html` — include HTMX 2.x
  via CDN `<script src="https://unpkg.com/htmx.org@2/dist/htmx.min.js">`, add
  three-panel layout with placeholder divs (id="panel-components",
  id="panel-jobs", id="panel-quality"), add workspace_id text input and JWT
  token text input with `localStorage` persistence via inline JS, set
  `hx-headers` on the body element to inject `Authorization: Bearer <token>`
  from localStorage on every HTMX request

**Checkpoint**: Foundation ready — schemas importable, HTML loads in browser
with three empty panels and a working token/workspace input form.

---

## Phase 3: User Story 1 — System Health Overview (Priority: P1) 🎯 MVP

**Goal**: Any workspace member can open the dashboard and immediately see
health status for all system components.

**Independent Test**: Start the full stack (`make up`), open the dashboard,
enter a valid token and workspace ID, and confirm all 7 components (api,
ingest_worker, lint_worker, embedding_worker, graph_worker, database, broker)
show a "healthy" indicator. Stop one worker and wait for auto-refresh; confirm
it changes to "unreachable".

### Implementation for User Story 1

- [x] T004 [P] [US1] Implement `GET /components` endpoint in
  `app/api/v1/status.py` — call `celery_app.control.inspect(timeout=2).ping()`
  via `asyncio.get_running_loop().run_in_executor(None, lambda: ...)` to avoid
  blocking; call `redis_client.llen(queue_name)` for each queue (`ingest`,
  `lint`, `embedding`, `graph`); run `await db.execute(text("SELECT 1"))` for
  DB health; call `redis_client.ping()` for broker health; return
  `ComponentsResponse` with one `ComponentStatus` per component

- [x] T005 [P] [US1] Add health panel to `app/static/status.html` inside
  `div#panel-components` — `hx-get="/api/v1/workspaces/{ws}/status/components"`,
  `hx-trigger="load, every 20s"`, render each `ComponentStatus` as a row with
  a colored badge (green=healthy, orange=degraded, red=unreachable), display
  `queue_depth` for worker rows, display `generated_at` as "Last updated: X"
  footer inside the panel

**Checkpoint**: US1 fully functional and independently testable — dashboard
health panel shows live component status updating every 20 seconds.

---

## Phase 4: User Story 2 — Ingest Job Monitoring (Priority: P2)

**Goal**: An editor can track any ingest or lint job from the last 24 hours,
including failure reason and retry count.

**Independent Test**: Trigger `POST /api/v1/workspaces/{ws}/ingest` with a
valid source, reload the jobs panel, confirm the job appears with status
`queued` or `running`. Trigger an ingest with an invalid source, wait for
failure, confirm the jobs panel shows `failed` with the error message visible.

### Implementation for User Story 2

- [x] T006 [P] [US2] Implement `GET /jobs` endpoint in `app/api/v1/status.py`
  — query `IngestJob` and `LintRun` tables for the workspace where `created_at
  > now() - interval 24h`, join `Source.display_name` on the first source_id
  for ingest jobs (append `+N more` if multiple), compute `duration_seconds`
  from `started_at`/`completed_at`, truncate `error_message` to 500 chars,
  return `JobsResponse` with `total_running`, `total_queued`,
  `total_failed_24h` aggregate counts; support optional `status` query param
  filter and `limit` (1–100, default 50)

- [x] T007 [P] [US2] Add jobs panel to `app/static/status.html` inside
  `div#panel-jobs` — `hx-get` to `/jobs`, `hx-trigger="load, every 20s"`,
  show summary row (X running / Y queued / Z failed), render jobs as a table
  with columns: queue, source_name, status (color-coded badge), duration,
  started_at; make failed rows expandable on click to reveal `error_message`
  and retry count; display `generated_at` timestamp footer

**Checkpoint**: US1 AND US2 both functional — jobs panel tracks live ingest
job lifecycle including failures with error details.

---

## Phase 5: User Story 3 — Knowledge Quality Monitoring (Priority: P3)

**Goal**: An admin can see wiki pages with semantic drift and the latest lint
findings without using the API directly. A platform admin can see an
aggregated view across all workspaces.

**Independent Test**: Create a wiki page, update it via ingest so
`embedding` diverges from `original_embedding` past the configured threshold,
reload the quality panel, confirm the page appears in drift alerts with correct
severity. Verify that with no alerts the panel shows "No issues found".

### Implementation for User Story 3

- [x] T008 [P] [US3] Implement `GET /quality` endpoint in
  `app/api/v1/status.py` — run pgvector query:
  `SELECT id, slug, title, (original_embedding <=> embedding) AS drift_score
  FROM wiki_pages WHERE workspace_id = :ws AND (original_embedding <=>
  embedding) > :threshold ORDER BY drift_score DESC LIMIT 50`; assign severity
  `error` when `drift_score > threshold * 2`, else `warning`; fetch most recent
  `LintRun` for workspace, join top-20 `LintFinding` records ordered by
  severity (error→warning→info); return `QualityResponse` with `lint_summary:
  null` when no lint run exists

- [x] T009 [P] [US3] Implement `GET /api/v1/admin/status` endpoint in
  `app/api/v1/status.py` (separate route outside the workspace prefix) —
  verify `current_user.is_platform_admin` (raise HTTP 403 otherwise); for each
  workspace aggregate `active_jobs` (status in queued/running), `failed_jobs_24h`,
  `drift_alert_count` (pages where drift > threshold), `lint_finding_count`
  (from most recent lint run); return `AdminStatusResponse`

- [x] T010 [P] [US3] Add quality panel to `app/static/status.html` inside
  `div#panel-quality` — `hx-get` to `/quality`, `hx-trigger="load, every 20s"`,
  render drift alerts as a list sorted by severity with drift_score displayed
  as a numeric badge (red for error ≥ 0.70, yellow for warning); render lint
  findings as a list with finding_type and severity badges; show "No issues
  found" empty state when both lists are empty; display `generated_at` footer

- [x] T011 [US3] Add admin "All Workspaces" tab to `app/static/status.html`
  — add tab visible only when `localStorage.getItem("platform_admin") ===
  "true"` (set by the token input form after decoding the JWT payload); tab
  body contains an `hx-get="/api/v1/admin/status"`, `hx-trigger="load, every
  30s"` div; render `WorkspaceStatusSummary` rows as a table with workspace
  slug, active_jobs, failed_jobs_24h, drift_alert_count, lint_finding_count

**Checkpoint**: All three user stories independently functional — quality panel
surfaces drift alerts with correct severity; admin tab visible and functional
for platform admins.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Observability, error resilience, and quality gates.

- [x] T012 Add structured logging to all 4 new endpoints in
  `app/api/v1/status.py` using `logger.info("event_name", key=value)` format:
  `status.components.request`, `status.jobs.request`, `status.quality.request`,
  `status.admin.request` on entry; `status.components.response`,
  `status.jobs.response`, `status.quality.response`, `status.admin.response`
  on success with relevant count fields

- [x] T013 Add error handling in `app/api/v1/status.py` so status endpoints
  never return HTTP 500 — wrap Celery inspect call in try/except so that when
  it raises or returns None all workers are marked `unreachable`; wrap
  `redis_client.llen` in try/except marking broker `unreachable` on failure;
  wrap DB health `SELECT 1` in try/except marking database `unreachable`;
  endpoint MUST always return 200 with degraded component entries rather than
  propagating exceptions

- [x] T014 [P] Run `make lint` (ruff + mypy) against `app/api/v1/status.py`
  and `app/schemas/status.py` and resolve all findings

- [ ] T015 [P] Run quickstart.md validation curl commands from
  `specs/001-status-web-gui/quickstart.md` against the running stack and
  confirm all 4 endpoints return valid JSON with no 4xx/5xx errors

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 ✅ — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — no dependency on US2 or US3
- **US2 (Phase 4)**: Depends on Phase 2 — no dependency on US1 or US3
- **US3 (Phase 5)**: Depends on Phase 2 — T011 depends on T009
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: Independent after Phase 2
- **US2 (P2)**: Independent after Phase 2 — can run concurrently with US1
- **US3 (P3)**: Independent after Phase 2 — T011 waits on T009; rest concurrent

### Within Each User Story

- Backend endpoint (T004/T006/T008/T009) and HTML panel (T005/T007/T010/T011)
  are parallel within their user story (different files)
- Polish (T012, T013) are sequential — both modify `app/api/v1/status.py`
- T014 and T015 can run in parallel after T012 and T013

### Parallel Opportunities

```bash
# Phase 2 — launch both together:
Task: T002  # app/schemas/status.py
Task: T003  # app/static/status.html shell

# Phase 3 (US1) — launch together:
Task: T004  # /components endpoint
Task: T005  # health panel HTML

# Phase 4 (US2) — launch together:
Task: T006  # /jobs endpoint
Task: T007  # jobs panel HTML

# Phase 5 (US3) — launch together:
Task: T008  # /quality endpoint
Task: T009  # /admin/status endpoint
Task: T010  # quality panel HTML
# T011 waits for T009

# Phase 6 — launch together after T012 and T013:
Task: T014  # make lint
Task: T015  # quickstart validation
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002, T003 in parallel)
3. Complete Phase 3: US1 (T004, T005 in parallel)
4. **STOP and VALIDATE**: Open dashboard, confirm health panel works end-to-end
5. Ship MVP — engineers can now see system health in a browser

### Incremental Delivery

1. Setup + Foundational → wired shell ready
2. US1 → health panel live (MVP)
3. US2 → job monitoring added
4. US3 → quality monitoring + admin view added
5. Polish → logging, error handling, lint, validation

### Parallel Team Strategy

With two developers after Phase 2:

- **Developer A**: T004 (backend) → T006 (backend) → T008, T009 (backend)
- **Developer B**: T005 (frontend) → T007 (frontend) → T010, T011 (frontend)

Backend and frontend for each story can merge independently.

---

## Notes

- `[P]` tasks = different files, no blocking dependencies within the phase
- `[US?]` label maps task to user story for traceability
- T004 uses `asyncio.get_running_loop().run_in_executor()` — do NOT use
  `asyncio.run()` inside an async FastAPI endpoint (that would violate
  Constitution Principle III)
- `original_embedding <=> embedding` uses pgvector cosine distance — confirm
  the `wiki_pages` model has both `original_embedding` and `embedding` columns
  before implementing T008
- Admin tab visibility in T011 uses client-side JWT payload inspection (base64
  decode of the payload segment) — no server round-trip needed to show/hide the tab
- Commit after each task or logical group; each Phase checkpoint is a good commit point
