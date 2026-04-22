# Implementation Plan: Documentation & Sources Browser GUI

**Branch**: `002-docs-browser-gui` | **Date**: 2026-04-22 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/002-docs-browser-gui/spec.md`

## Summary

Add a browser-based documentation portal that lets users read wiki pages and audit ingested sources without API knowledge. The backend exposes a new unauthenticated read-only router (`/api/v1/public/`) backed by existing DB queries. The frontend is a Vite + React SPA with Markdown rendering served as a new `portal` Docker container behind Nginx.

## Technical Context

**Language/Version**: Python 3.12 (backend), Node.js 20 / TypeScript (portal frontend)  
**Primary Dependencies (backend)**: FastAPI, SQLAlchemy 2.0 async, PostgreSQL 16 (existing)  
**Primary Dependencies (frontend)**: Vite 5, React 18, react-markdown 9, remark-gfm, react-router-dom 6  
**Storage**: PostgreSQL 16 — no new tables; read-only queries against existing `wiki_pages`, `sources`, `workspaces`, `wiki_page_source_maps`  
**Testing**: pytest (backend unit + integration), Vitest (portal unit — optional v1)  
**Target Platform**: Desktop browser (Chrome, Firefox, Safari latest); served via Nginx container  
**Project Type**: Web application — read-only documentation portal consuming an existing REST API  
**Performance Goals**: Search results in < 2s for ≤ 500 pages (SC-004); page load in < 2s on local network  
**Constraints**: No auth for read-only access (FR-010); `PUBLIC_API_ENABLED` env guard; no new DB migrations  
**Scale/Scope**: Internal tool; dozens of users, hundreds of pages per workspace

## Constitution Check

*GATE: Must pass before implementation. Re-checked after Phase 1 design.*

| Principle | Applies? | Status | Notes |
|-----------|----------|--------|-------|
| I. LLM Wiki Pattern | ✅ | PASS | Portal reads from wiki pages — reinforces the wiki-first pattern; no raw source retrieval |
| II. Multi-Tenant Workspace Isolation | ✅ | PASS | All public endpoints are scoped by `workspace_id`; no cross-workspace queries possible |
| III. Async Worker Architecture | N/A | — | No new Celery workers; frontend has no workers |
| IV. Knowledge Quality Controls | N/A | — | Portal is read-only; no write path, no gate needed |
| V. Observability & Structured Logging | ✅ | PASS | New public router MUST use `logger.info("event_name", key=value)` — enforced in contracts |
| VI. Test Discipline | ✅ | PASS | New `app/api/v1/public.py` MUST have `tests/unit/test_public_router.py` and `tests/integration/test_public_endpoints.py` |

**Post-design re-check**: All six gates pass. No violations. No complexity tracking entry needed.

## Project Structure

### Documentation (this feature)

```text
specs/002-docs-browser-gui/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── public-api.md    # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code

```text
# Backend addition (Python)
app/api/v1/
└── public.py                        # New unauthenticated read-only router

app/api/
└── router.py                        # Register /api/v1/public prefix (edit)

app/core/
└── config.py                        # Add PUBLIC_API_ENABLED setting (edit)

tests/unit/
└── test_public_router.py            # Unit tests for query helpers

tests/integration/
└── test_public_endpoints.py         # Integration tests against real PostgreSQL

# Frontend (portal SPA)
portal/
├── src/
│   ├── api/
│   │   └── client.ts                # Typed fetch wrappers for all public endpoints
│   ├── components/
│   │   ├── Layout.tsx               # Navigation shell + workspace picker
│   │   ├── PageViewer.tsx           # Markdown renderer (react-markdown + remark-gfm)
│   │   ├── SourcesList.tsx          # Sources table with status badges
│   │   └── SearchBar.tsx            # Search input + results dropdown
│   ├── pages/
│   │   ├── WorkspaceHome.tsx        # Page list view
│   │   ├── PageView.tsx             # Full page view
│   │   └── SourcesView.tsx          # Sources list + source→pages drill-down
│   └── main.tsx
├── Dockerfile                       # Multi-stage: node build → nginx:alpine serve
├── nginx.conf                       # Proxy /api to api:8000; serve SPA on /
├── package.json
└── vite.config.ts                   # Dev proxy: /api → http://localhost:8000

# Docker
docker-compose.yml                   # Add portal service (port 3000) (edit)
```

**Structure Decision**: Web application with separate backend extension and frontend SPA. The portal is a self-contained directory at repo root. The backend addition is minimal — a single new router file + config change + test files. No changes to existing routers, models, or workers.

## Phase 0: Research Findings

All unknowns resolved. See [research.md](research.md) for full rationale.

**Summary of decisions**:
- Frontend: Vite + React SPA (open-source, maintained, dynamic API-backed)
- Public API: New `/api/v1/public/` router, no auth, `PUBLIC_API_ENABLED` guard
- Search: PostgreSQL ILIKE on existing `wiki_pages.content` + `wiki_pages.title`
- Serving: Nginx container proxying `/api` to API container (portal on port 3000)
- Source→pages: New `GET /api/v1/public/workspaces/{id}/sources/{source_id}/pages` endpoint

## Phase 1: Design Artifacts

### Data Model

See [data-model.md](data-model.md).

- **No new DB tables or migrations**
- Reuses: `Workspace`, `WikiPage`, `Source`, `WikiPageSourceMap`
- New Pydantic schemas (inline in `public.py`): `WorkspacePublicResponse`, `WikiPagePublicResponse`, `WikiPageDetailPublicResponse`, `SourcePublicResponse`, `SourcePagesResponse`, `SearchResultItem`, `SearchResponse`
- `SourcePublicResponse` adds `created_at` field (omitted from original `SourceResponse`)

### API Contracts

See [contracts/public-api.md](contracts/public-api.md).

New endpoints under `/api/v1/public/`:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/workspaces` | List all workspaces |
| GET | `/workspaces/{workspace_id}/pages` | List pages (paginated, filterable by type) |
| GET | `/workspaces/{workspace_id}/pages/{page_path:path}` | Get single page with content |
| GET | `/workspaces/{workspace_id}/sources` | List sources (filterable by status) |
| GET | `/workspaces/{workspace_id}/sources/{source_id}/pages` | Pages produced by a source |
| GET | `/workspaces/{workspace_id}/search?q=` | Full-text keyword search |

### Portal Component Map

```
Layout (persistent)
├── WorkspacePicker  →  WorkspaceHome
│                         ├── SearchBar
│                         └── PageList
│                               └── PageView (react-markdown)
└── SourcesView
      └── SourceRow → [click] → SourcePagesPanel
```

### CORS

Development: API's `CORSMiddleware` allows `http://localhost:5173`.  
Production: No CORS needed — Nginx serves both portal and proxies `/api` on same origin.

### Quickstart

See [quickstart.md](quickstart.md).

## Implementation Order

This is the dependency-ordered sequence for task generation:

1. **Backend: config + router scaffold** — `PUBLIC_API_ENABLED` setting + empty `public.py` registered in `router.py`
2. **Backend: list/get endpoints** — workspaces, pages list, single page
3. **Backend: sources endpoints** — sources list, source→pages map
4. **Backend: search endpoint** — ILIKE query + `SearchResponse` schema
5. **Backend: unit tests** — `test_public_router.py` covering query helpers
6. **Backend: integration tests** — `test_public_endpoints.py` against real PostgreSQL
7. **Portal: project scaffold** — `portal/` with Vite + React + routing skeleton
8. **Portal: API client** — typed `client.ts` for all 6 endpoints
9. **Portal: WorkspaceHome + PageList** — workspace picker + page list (P1)
10. **Portal: PageViewer** — Markdown rendering via react-markdown + remark-gfm (P1)
11. **Portal: SourcesView** — sources table + status badges + source→pages drill-down (P2)
12. **Portal: SearchBar** — search input + results dropdown (P3)
13. **Portal: multi-workspace navigation** — workspace switcher in Layout (P4)
14. **Docker: portal service** — `Dockerfile` + `nginx.conf` + `docker-compose.yml` edit
15. **CORS: development config** — add `localhost:5173` to CORSMiddleware origins
