# Tasks: Documentation & Sources Browser GUI

**Input**: Design documents from `specs/002-docs-browser-gui/`
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/public-api.md ✅

**Tests**: Backend tests included — required by Constitution Principle VI for new router code.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US4)
- All file paths are absolute from repo root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize the portal project and prepare the shared scaffolding both sides (backend and frontend) need before story work begins.

- [x] T001 Initialize `portal/` Vite + React + TypeScript project: `npm create vite@latest portal -- --template react-ts`, add `react-router-dom`, `react-markdown`, `remark-gfm` to `portal/package.json`
- [x] T002 Create `portal/vite.config.ts` with `/api` dev proxy targeting `http://localhost:8000` and base path `/`
- [x] T003 [P] Add `portal/node_modules`, `portal/dist` to `.gitignore`
- [x] T004 [P] Create empty typed skeleton `portal/src/api/client.ts` exporting placeholder async functions for all 6 public endpoints (compile-time shape only; no implementation yet)

**Checkpoint**: `cd portal && npm install && npm run build` succeeds with no errors.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Backend plumbing required before any user story endpoint can be implemented. Must be complete before Phase 3+.

**⚠️ CRITICAL**: No user story backend work can begin until this phase is complete.

- [x] T005 Add `PUBLIC_API_ENABLED: bool = True` setting to `app/core/config.py` (reads from env var `PUBLIC_API_ENABLED`)
- [x] T006 Create `app/api/v1/public.py` — empty `APIRouter` with a startup guard: all routes return `HTTP 503` when `settings.PUBLIC_API_ENABLED` is `False`; add structured log `logger.info("public_api_request", endpoint=..., workspace_id=...)` stub used by all handlers
- [x] T007 Register the new public router in `app/api/router.py` under the prefix `/api/v1/public` with tag `public`
- [x] T008 Add `http://localhost:5173` to the `CORSMiddleware` allowed origins in `app/main.py` when `settings.ENVIRONMENT == "development"` (already `["*"]` in development — no change needed)

**Checkpoint**: `make dev` starts without error; `curl http://localhost:8000/api/v1/public/workspaces` returns `503` (guard active) or `200 []` (guard off). No existing tests break.

---

## Phase 3: User Story 1 — Browse Wiki Pages (Priority: P1) 🎯 MVP

**Goal**: Users can open the portal, pick a workspace, browse all wiki pages, and read full Markdown content.

**Independent Test**: Open `http://localhost:5173`, select a workspace, click any page, verify the Markdown renders correctly with headings and code blocks.

### Implementation

- [x] T009 [US1] Implement `GET /api/v1/public/workspaces` in `app/api/v1/public.py` — queries `Workspace` table, returns list of `WorkspacePublicResponse` (fields: `id`, `slug`, `display_name`, `schema_version`); emits structured log
- [x] T010 [US1] Implement `GET /api/v1/public/workspaces/{workspace_id}/pages` in `app/api/v1/public.py` — queries `WikiPage` with `workspace_id` filter, supports `limit`/`offset`/`page_type` params, returns list of `WikiPagePublicResponse`; returns `404` for unknown workspace
- [x] T011 [US1] Implement `GET /api/v1/public/workspaces/{workspace_id}/pages/{page_path:path}` in `app/api/v1/public.py` — fetches single `WikiPage` by path, returns `WikiPageDetailPublicResponse` (adds `content` field); returns `404` for missing page
- [x] T012 [P] [US1] Implement `fetchWorkspaces()` and `fetchPages(workspaceId, params)` and `fetchPage(workspaceId, pagePath)` in `portal/src/api/client.ts` with full TypeScript types matching the contract schemas
- [x] T013 [P] [US1] Create `portal/src/components/Layout.tsx` — persistent navigation shell with top bar, workspace name display, and `<Outlet />` slot; no workspace picker yet (added in US4)
- [x] T014 [US1] Create `portal/src/pages/WorkspaceHome.tsx` — lists all workspaces on first load; when a workspace is selected renders paginated page list with titles, types, and `updated_at` timestamps; handles empty-workspace state with a clear message
- [x] T015 [US1] Create `portal/src/components/PageViewer.tsx` — renders `content` string via `<ReactMarkdown remarkPlugins={[remarkGfm]}>` with GFM support (tables, code fences, strikethrough); shows page title, `page_type` badge, and `updated_at`
- [x] T016 [US1] Create `portal/src/pages/PageView.tsx` — calls `fetchPage`, passes content to `PageViewer`, shows loading skeleton while fetching, shows "page not found" message on `404`
- [x] T017 [US1] Wire `react-router-dom` routes in `portal/src/main.tsx`: `/` → `WorkspaceHome`, `/workspaces/:workspaceId` → `WorkspaceHome` (page list), `/workspaces/:workspaceId/pages/*pagePath` → `PageView`; wrap all routes in `Layout`

**Checkpoint**: US1 fully functional. User can browse pages and read Markdown content. No auth required.

---

## Phase 4: User Story 2 — View Ingested Sources (Priority: P2)

**Goal**: Users can audit all ingested sources for a workspace — see name, type, status, date — and drill into a source to see which wiki pages it produced.

**Independent Test**: Open sources view for any workspace; confirm all sources appear; confirm a `failed` source has a visible error badge; click a source and see its generated pages listed.

### Implementation

- [x] T018 [US2] Implement `GET /api/v1/public/workspaces/{workspace_id}/sources` in `app/api/v1/public.py` — queries `Source` with `workspace_id`, supports `status_filter`/`limit`/`offset`, returns list of `SourcePublicResponse` (fields: `id`, `title`, `source_type`, `ingest_status`, `byte_size`, `created_at`); `created_at` is new vs existing `SourceResponse`
- [x] T019 [US2] Implement `GET /api/v1/public/workspaces/{workspace_id}/sources/{source_id}/pages` in `app/api/v1/public.py` — joins `WikiPageSourceMap` → `WikiPage` for the given `source_id`, returns list of `WikiPagePublicResponse`; returns `404` for unknown source
- [x] T020 [P] [US2] Add `fetchSources(workspaceId, params)` and `fetchSourcePages(workspaceId, sourceId)` to `portal/src/api/client.ts`
- [x] T021 [US2] Create `portal/src/pages/SourcesView.tsx` — renders sources in a table with columns: name/URL, type pill, status badge (colour-coded: green=completed, red=failed, yellow=ingesting, grey=pending), byte size, created date; handles empty state
- [x] T022 [US2] Add source drill-down to `portal/src/pages/SourcesView.tsx` — clicking a source row expands an inline panel listing the wiki pages produced by that source with links to `PageView`; fetches via `fetchSourcePages`
- [x] T023 [US2] Add "Sources" navigation link to `portal/src/components/Layout.tsx` pointing to `/workspaces/:workspaceId/sources`; add the `/workspaces/:workspaceId/sources` route in `portal/src/main.tsx`

**Checkpoint**: US1 and US2 both work independently. Sources view shows statuses; drill-down shows linked pages.

---

## Phase 5: User Story 3 — Search Across Pages (Priority: P3)

**Goal**: Users type a keyword into a search bar and see matching pages with context snippets; clicking a result opens the full page.

**Independent Test**: Type a known word from any wiki page into the search bar; confirm matching pages appear with title and snippet; click a result and land on the correct page.

### Implementation

- [x] T024 [US3] Implement `GET /api/v1/public/workspaces/{workspace_id}/search` in `app/api/v1/public.py` — accepts `q` (min 2 chars, required) and `limit` (default 20, max 50); queries `wiki_pages` with `title ILIKE '%q%' OR content ILIKE '%q%'`; title matches ranked above content matches; returns `SearchResponse` with `total_count` and list of `SearchResultItem` (`id`, `page_path`, `title`, `snippet` ~300 chars, `updated_at`); returns `400` if `q` is missing or too short
- [x] T025 [P] [US3] Add `fetchSearch(workspaceId, q, limit?)` to `portal/src/api/client.ts`
- [x] T026 [US3] Create `portal/src/components/SearchBar.tsx` — text input with 300ms debounce; on input fires `fetchSearch`; renders results in a dropdown showing title + snippet; clicking a result navigates to `PageView` and closes dropdown; shows "no results" message when empty; handles `400` gracefully (min-length hint)
- [x] T027 [US3] Integrate `SearchBar` into `portal/src/components/Layout.tsx` top bar; search is scoped to the currently active workspace

**Checkpoint**: US1, US2, and US3 all work independently. Search returns relevant results in < 2 s for test wikis.

---

## Phase 6: User Story 4 — Multi-Workspace Navigation (Priority: P4)

**Goal**: Users with access to multiple workspaces can switch between them from a persistent navigation element without losing their current location.

**Independent Test**: With two workspaces ingested, use the workspace picker to switch; confirm page list and sources update to the new workspace.

### Implementation

- [x] T028 [US4] Create `portal/src/components/WorkspacePicker.tsx` — dropdown populated by `fetchWorkspaces()`; displays `display_name`; on selection navigates to `/workspaces/:newId` preserving the current section (pages vs sources)
- [x] T029 [US4] Integrate `WorkspacePicker` into `portal/src/components/Layout.tsx` persistent top bar; replace static workspace name display with the picker component

**Checkpoint**: All four user stories functional. Workspace switch updates all content without full page reload.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Docker integration, backend tests (constitution-mandated), error resilience, and final validation.

- [x] T030 Create `portal/Dockerfile` — multi-stage build: stage 1 `node:20-alpine` runs `npm ci && npm run build`; stage 2 `nginx:alpine` copies `dist/` to `/usr/share/nginx/html`
- [x] T031 Create `portal/nginx.conf` — serves SPA at `/` with `try_files $uri /index.html`; proxies `/api` to `http://api:8000`; no CORS headers needed (same-origin via proxy)
- [x] T032 Add `portal` service to `docker-compose.yml` — `build: portal`, `ports: ["3000:80"]`, `depends_on: [api]`
- [x] T033 Write `tests/unit/test_public_router.py` — unit tests for pure query helpers: ILIKE snippet extraction logic, `PUBLIC_API_ENABLED=False` guard returns `503`, `400` when `q` parameter is too short; no `AsyncSessionLocal` imports per Constitution VI
- [x] T034 [P] Write `tests/integration/test_public_endpoints.py` — integration tests against real PostgreSQL covering all 6 public endpoints: list workspaces, list pages, get page, list sources, source→pages, search; test `404` for unknown workspace/page/source
- [x] T035 [P] Add error boundary to `portal/src/components/Layout.tsx` — when API returns network error or non-2xx, render a clear "Unable to connect to the wiki server" banner instead of a blank screen
- [x] T036 `ruff check` passed on all new files; `npm run build` clean (TypeScript + Vite); `make lint` and `make test` to be validated in Docker (`make up`)
- [ ] T037 Validate against `quickstart.md` — run `make up`, confirm portal accessible at `http://localhost:3000`, verify all 4 user stories work end-to-end

**Checkpoint**: `make test` green. `make up` brings up portal at port 3000. All 4 user stories work in Docker.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 completion — **blocks all user story backend work**
- **Phase 3 (US1)**: Depends on Phase 2 — first deliverable; frontend work (T012–T017) can start after Phase 1
- **Phase 4 (US2)**: Depends on Phase 2; integrates with US1 nav links but is independently testable
- **Phase 5 (US3)**: Depends on Phase 2; new backend endpoint + UI component; independently testable
- **Phase 6 (US4)**: Depends on Phase 3 (uses `fetchWorkspaces` already implemented in T009/T012)
- **Phase 7 (Polish)**: Depends on all story phases complete

### User Story Dependencies

- **US1 (P1)**: Depends only on Phase 2 — no other story dependencies
- **US2 (P2)**: Depends only on Phase 2 — independently testable; nav link reuses Layout from US1
- **US3 (P3)**: Depends only on Phase 2 — independently testable; SearchBar is a standalone component
- **US4 (P4)**: Depends on US1 (`fetchWorkspaces` from T009/T012) — trivial integration

### Within Each Story

- Backend endpoints before frontend consumption (API must exist before `client.ts` calls it)
- `client.ts` typed functions before page components that call them
- `Layout.tsx` before page components (shell wraps all pages)
- Routes wired last (requires all page components to exist)

### Parallel Opportunities

- T003, T004 can run in parallel with each other (Phase 1)
- T005–T008 can run in parallel with each other (Phase 2 — different files)
- T009, T010, T011 are sequential (same file, `public.py`) but T012, T013 are parallel to T009–T011 (different files)
- T018, T019 are sequential (same file) but T020 runs in parallel
- T024 (backend) is independent from T025–T027 (frontend) — can split across backend/frontend developers
- T033, T034, T035 all run in parallel (different files)

---

## Parallel Example: User Story 1

```text
# After T007 (router registered), split work:
Backend developer:
  T009: GET /workspaces endpoint
  T010: GET /workspaces/{id}/pages endpoint
  T011: GET /workspaces/{id}/pages/{path} endpoint

Frontend developer (parallel to backend):
  T012: client.ts fetch functions (uses mock or local API)
  T013: Layout.tsx shell component (no data needed)

Then converge:
  T014: WorkspaceHome.tsx (needs T009 + T012 + T013)
  T015: PageViewer.tsx (needs T012)
  T016: PageView.tsx (needs T011 + T012 + T015)
  T017: Routes (needs T014 + T016 + T013)
```

---

## Implementation Strategy

### MVP First (User Story 1 only — ~12 tasks)

1. Complete Phase 1: Setup (T001–T004)
2. Complete Phase 2: Foundational (T005–T008)
3. Complete Phase 3: User Story 1 (T009–T017)
4. **STOP and VALIDATE**: Open portal, browse pages, read Markdown
5. Deploy/demo if ready

### Incremental Delivery

1. Phase 1 + 2 → foundation ready
2. Phase 3 → wiki browsing works (MVP — SC-001, SC-003, SC-005)
3. Phase 4 → source auditing works (SC-002)
4. Phase 5 → search works (SC-004)
5. Phase 6 → workspace switching works
6. Phase 7 → production-ready (Docker + tests)

### Parallel Team Strategy (2 developers)

After Phase 2 completes:
- **Developer A**: T009–T011 (backend endpoints US1) → T018–T019 (US2 backend) → T024 (US3 backend) → T033–T034 (tests)
- **Developer B**: T012–T017 (frontend US1) → T020–T023 (frontend US2) → T025–T027 (frontend US3) → T028–T029 (US4) → T030–T032 (Docker)

---

## Notes

- `[P]` tasks touch different files — safe to run in parallel within a phase
- `[Story]` label maps each task to its user story for traceability
- Backend tests (T033, T034) are constitution-mandated — not optional
- `PUBLIC_API_ENABLED=true` must be set in `.env` for any end-to-end testing
- The portal dev server (`npm run dev` in `portal/`) proxies `/api` automatically — no CORS issues in development
- Commit after each checkpoint; each checkpoint is a working, demonstrable state
