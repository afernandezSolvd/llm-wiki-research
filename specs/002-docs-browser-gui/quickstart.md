# Quickstart: Documentation Portal (002-docs-browser-gui)

## Prerequisites

- Docker + Docker Compose (for the full stack)
- Node.js 20+ (for local portal development)
- The existing stack running: `make up`

---

## Running the Portal in Development

### 1. Start the backend

```bash
make up
```

The API will be available at `http://localhost:8000`. Confirm it is healthy:

```bash
curl http://localhost:8000/health
```

### 2. Enable public API

In your `.env` (or `.env.local`), ensure:

```
PUBLIC_API_ENABLED=true
```

This is the default in `docker-compose.yml`. Restart the API container if you change it:

```bash
docker compose restart api
```

### 3. Start the portal dev server

```bash
cd portal
npm install
npm run dev
```

The portal will open at `http://localhost:5173`. It proxies all `/api` requests to `http://localhost:8000` automatically (configured in `vite.config.ts`).

---

## Running with Docker Compose (full stack)

```bash
make up
```

The portal container builds and serves at `http://localhost:3000`.

To rebuild the portal container after frontend changes:

```bash
docker compose build portal && docker compose up -d portal
```

---

## Project Structure

```
portal/
├── src/
│   ├── api/
│   │   └── client.ts          # Typed fetch wrappers for all public endpoints
│   ├── components/
│   │   ├── Layout.tsx          # Navigation shell + workspace picker
│   │   ├── PageViewer.tsx      # Markdown renderer
│   │   ├── SourcesList.tsx     # Sources table with status badges
│   │   └── SearchBar.tsx       # Search input + results dropdown
│   ├── pages/
│   │   ├── WorkspaceHome.tsx   # Page list for a workspace
│   │   ├── PageView.tsx        # Full page view
│   │   └── SourcesView.tsx     # Sources list + source→pages drill-down
│   └── main.tsx
├── Dockerfile
├── nginx.conf
├── package.json
└── vite.config.ts
```

---

## Backend Structure Added

```
app/api/v1/
└── public.py                  # New unauthenticated read-only router

tests/
├── unit/
│   └── test_public_router.py  # Unit tests for query helpers
└── integration/
    └── test_public_endpoints.py
```

The new router is registered in `app/api/router.py` under the `/api/v1/public` prefix.

---

## Verifying the Public API

```bash
# List workspaces
curl http://localhost:8000/api/v1/public/workspaces

# List pages in a workspace
curl http://localhost:8000/api/v1/public/workspaces/<workspace_id>/pages

# Fetch a page
curl http://localhost:8000/api/v1/public/workspaces/<workspace_id>/pages/company/overview

# Search
curl "http://localhost:8000/api/v1/public/workspaces/<workspace_id>/search?q=overview"
```

---

## Running Tests

```bash
# All tests (unit + integration)
make test

# Public router unit tests only
pytest tests/unit/test_public_router.py -v

# Public endpoint integration tests (requires running PostgreSQL)
pytest tests/integration/test_public_endpoints.py -v
```

---

## Disabling the Public API

Set in `.env`:

```
PUBLIC_API_ENABLED=false
```

All `/api/v1/public/*` routes will return `503 Service Unavailable`. The portal will display a "Portal is currently unavailable" message.
