# Research: Status Web GUI

**Branch**: `001-status-web-gui` | **Phase**: 0 | **Date**: 2026-04-21

## Decision 1: Frontend Delivery Approach

**Decision**: Static HTML served from FastAPI's `StaticFiles` mount, using
HTMX (via CDN) for declarative partial auto-refresh and vanilla JS for
minimal interactivity.

**Rationale**: The spec requires no separate deployment. Serving a single
`status.html` from the existing FastAPI process at `/status` satisfies this
with zero build pipeline. HTMX's `hx-trigger="every 20s"` handles polling
without writing JavaScript loop logic. The file is loadable directly in a
browser even without the server (for visual QA).

**Alternatives considered**:
- React SPA: rejected — requires Node.js build step, separate deployment
  concern, and a bundler. Overkill for a read-only status page.
- Jinja2 server-side templates: rejected — full-page re-renders produce a
  flicker on every auto-refresh cycle. Partial updates via HTMX are smoother.
- WebSockets / Server-Sent Events: rejected — polling at 20s is sufficient
  for a status dashboard and avoids a persistent connection per open browser
  tab at scale.

## Decision 2: Worker Health Querying

**Decision**: Use `celery_app.control.inspect(timeout=2).ping()` called from
a `run_in_executor` wrapper inside the async FastAPI endpoint to avoid
blocking the event loop.

**Rationale**: `inspect().ping()` broadcasts to all workers and collects
responses within the timeout. A 2-second timeout is generous enough for
healthy workers on localhost/LAN but short enough to not stall the dashboard
response. Workers that do not respond within the window are reported as
unreachable.

**Pattern**:
```python
loop = asyncio.get_running_loop()
result = await loop.run_in_executor(
    None, lambda: celery_app.control.inspect(timeout=2).ping()
)
```

**Alternatives considered**:
- Custom Redis heartbeat keys written by workers: rejected — adds worker code
  changes and a new Redis key schema to maintain.
- Celery Events API: rejected — requires a persistent event consumer process,
  which is operational overhead beyond Flower's existing role.

## Decision 3: Queue Depth Measurement

**Decision**: Query Redis `LLEN` on each queue name (`ingest`, `lint`,
`embedding`, `graph`) using the existing synchronous `get_redis_pool()` client.

**Rationale**: Celery uses Redis lists as the default queue store. `LLEN` on
the queue key gives the number of pending (not-yet-consumed) tasks. This is
a single fast O(1) Redis read per queue. The existing `get_redis_pool()`
already provides a synchronous Redis connection — no new client is needed.

**Note**: The Redis key for a Celery queue is the queue name itself (e.g.,
`"ingest"`) when using the default Redis broker configuration. Confirm via
`redis-cli KEYS *` against a running stack if queue keys differ in practice.

**Alternatives considered**:
- Celery inspect `reserved()` / `active()`: gives task-level detail but
  requires a worker broadcast round-trip per call. LLEN is cheaper and
  sufficient for a depth count.

## Decision 4: Semantic Drift Data

**Decision**: Query `wiki_pages` with pgvector's cosine distance operator
`<=>` between `original_embedding` and `embedding` (current), filtered by
workspace and threshold.

```sql
SELECT id, slug, title,
       (original_embedding <=> embedding) AS drift_score
FROM wiki_pages
WHERE workspace_id = :workspace_id
  AND (original_embedding <=> embedding) > :threshold
ORDER BY drift_score DESC
LIMIT 50;
```

Pages where `drift_score > threshold` → severity `warning`.
Pages where `drift_score > threshold * 2` → severity `error`.

**Rationale**: The `original_embedding` field is the immutable anchor per the
constitution. The current embedding is named `embedding` (the standard field
name in the model, updated on each ingest). The `<=>` operator is pgvector's
cosine distance, matching how drift is defined in the system.

**Alternatives considered**:
- Pre-computing and storing drift scores: rejected — adds a derived column
  that must be kept in sync. The query is cheap enough to run on demand for
  a status dashboard with a 30-second refresh.

## Decision 5: Lint Quality Summary

**Decision**: Fetch the single most recent `LintRun` for the workspace, then
query its `LintFinding` records grouped by severity and type.

**Rationale**: The spec shows "most recent lint run" findings on the quality
panel. Joining `lint_runs` and `lint_findings` on `lint_run_id` with a
`WHERE lint_run_id = (SELECT id FROM lint_runs WHERE workspace_id = :ws ORDER
BY created_at DESC LIMIT 1)` is a simple query with no schema changes.

## Decision 6: API Endpoint Design

**Decision**: Four new GET-only endpoints under
`/api/v1/workspaces/{workspace_id}/status/`:

| Path | Panel | Auth |
|---|---|---|
| `/components` | Worker + broker + DB health | workspace member |
| `/jobs` | Active + recent jobs (24h) | workspace member |
| `/quality` | Drift alerts + lint summary | workspace member |
| `/admin/status` | Cross-workspace aggregate | platform_admin only |

Separate endpoints per panel enable HTMX to refresh each panel independently
without re-fetching data the user is not currently viewing.

**Rationale**: One monolithic `/status` endpoint would force re-fetching all
data (including the slow Celery inspect call) on every panel's refresh cycle.
Splitting by panel lets the components panel (slow: ~2s Celery timeout) refresh
less frequently than the jobs panel (fast: DB query).

## Decision 7: Authentication Integration

**Decision**: Reuse the existing `get_current_user` + workspace membership
dependency chain already used by all other `/api/v1/workspaces/{workspace_id}/`
endpoints. No new auth logic required.

**Rationale**: All workspace endpoints already enforce JWT + membership. The
status endpoints are read-only and sit under the same path prefix, so the
same dependency applies automatically.
