# Research: Documentation & Sources Browser GUI

**Phase 0 output** | Feature: 002-docs-browser-gui | Date: 2026-04-22

---

## Decision 1: Frontend Framework

**Decision**: Vite + React SPA with `react-markdown` + `remark-gfm`

**Rationale**: The wiki content changes continuously (pages are created/updated by Celery ingest workers). Static site generators (Docusaurus, MkDocs, VitePress in static mode) generate content at build time — they cannot natively render live API data without a separate sync step. A React SPA fetches pages directly from the API at runtime, so the portal always reflects current wiki state without a rebuild. Vite is the lightweight, maintained open-source build tool in this space. `react-markdown` (MIT) is the standard open-source Markdown renderer for React.

**Alternatives considered**:
- **Docusaurus**: Best for static documentation committed to a repo. Not suited to API-backed dynamic content without a complex custom data plugin and periodic re-build. Rejected.
- **MkDocs Material**: Python-based, excellent UI, but fully static. Same dynamic-content problem. Rejected.
- **VitePress**: Vue-based, excellent docs theme. Also static-build oriented; custom SSR mode is complex. Rejected for simplicity.
- **Vanilla JS + marked.js** (like existing `status.html`): No build toolchain, but no component reuse or type safety. Rejected — too close to "built from scratch."

---

## Decision 2: Public Read-Only API Layer

**Decision**: New unauthenticated router at `/api/v1/public/` re-exposing a subset of existing endpoints.

**Rationale**: All existing wiki/sources/workspaces endpoints require a valid JWT (`get_current_user` dependency). FR-010 requires no authentication for read-only portal access. Creating a thin `/public` router that calls the same DB queries — but without the auth dependency — is the minimal-change approach. This keeps the authenticated API unchanged and makes the public surface explicit and auditable.

**Alternatives considered**:
- **Portal handles login**: The portal shows a login screen and stores a JWT. Violates FR-010 directly.
- **Shared API key for portal**: A static API key injected into the Nginx container. Slightly more complex secret management; still requires a backend code change. Rejected for unnecessary complexity.
- **Make existing endpoints optionally unauthenticated**: Adding `Optional[User]` to every existing endpoint is fragile. Rejected.

**Security note**: The `/public` router should be disabled in production environments via `PUBLIC_API_ENABLED=true/false` env var (defaults `true` in `docker-compose.yml`, should be `false` when external network access is possible). This is an internal-network assumption documented in the spec.

---

## Decision 3: Search Strategy

**Decision**: PostgreSQL full-text search (`tsvector` / `ILIKE`) via a new `GET /api/v1/public/workspaces/{id}/search?q=` endpoint.

**Rationale**: Pages are already stored in PostgreSQL with a `content` field. A simple `ILIKE '%query%'` on `title` and content will be adequate for v1 (wikis up to 500 pages per SC-004). No additional infrastructure (Elasticsearch, Meilisearch) needed. The SPA sends a search query to the API; the API returns matching pages with a snippet extracted server-side.

**Alternatives considered**:
- **Client-side search (Fuse.js)**: Would require downloading all page content to the browser. Impractical for large wikis; also leaks all content to clients.
- **pgvector semantic search**: Overkill for a keyword search box; adds latency and embedding cost. Rejected for v1.

---

## Decision 4: Portal Deployment & Serving

**Decision**: New `portal` Docker service (multi-stage Vite build → `nginx:alpine`). In development: `npm run dev` proxies `/api` to `localhost:8000`.

**Rationale**: Mirrors the existing container model. The Nginx container serves the built SPA as static files and proxies `/api/*` to the `api` container, so the SPA never has to deal with CORS. The API container needs CORS headers only for local development (`localhost:5173` → `localhost:8000`).

**Alternatives considered**:
- **Serve from FastAPI `StaticFiles`**: Requires building the portal and copying assets into `app/static/`. Mixes Python and Node build toolchains in one container. Harder to iterate on frontend. Rejected.
- **Serve from existing Nginx reverse proxy (if any)**: No reverse proxy exists in the current stack. The API container handles its own serving.

---

## Decision 5: Source → Pages Mapping

**Decision**: Expose `WikiPageSourceMap` in the public API as a separate endpoint: `GET /api/v1/public/workspaces/{id}/sources/{source_id}/pages`.

**Rationale**: The `WikiPageSourceMap` model already links `source_id → wiki_page_id`. The existing `SourceResponse` schema omits this relationship. Rather than bloating the source list response with a nested pages array, a dedicated endpoint is called lazily when the user drills into a source — consistent with the existing API design pattern.

---

## Existing Infrastructure Confirmed Available

| Need | Existing endpoint | Notes |
|------|------------------|-------|
| List workspaces | `GET /api/v1/workspaces` | Needs auth; public wrapper needed |
| List pages | `GET /api/v1/workspaces/{id}/wiki/pages` | Paginated; public wrapper needed |
| Get page content | `GET /api/v1/workspaces/{id}/wiki/pages/{path:path}` | Returns `WikiPageDetail` with `content` |
| List sources | `GET /api/v1/workspaces/{id}/sources` | Status filter available |
| Source→pages map | `WikiPageSourceMap` DB model | No existing API endpoint; new endpoint needed |
| Search | No existing search endpoint | New endpoint using PostgreSQL ILIKE |
