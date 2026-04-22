# Context Wiki Portal

Read-only web UI for browsing the Context wiki. Runs as a Docker service on port 3000.

## What It Is

A Vite + React + TypeScript SPA that connects to the public read-only API (`/api/v1/public/*`) and lets anyone browse wiki pages, inspect ingested sources, and search content — no login required.

## Quick Start

```bash
# Via Docker (recommended — starts with the full stack)
make up
open http://localhost:3000

# Local dev (requires the API to be running separately)
cd portal
npm install
npm run dev    # http://localhost:5173
```

## Features

- **Browse pages** — sidebar groups pages by type; click any page to read full Markdown with syntax-highlighted code blocks, tables, and GFM formatting
- **Sources view** — table of all ingested sources with colour-coded status badges (`completed` / `ingesting` / `failed` / `pending`); expand a row to see the pages it produced
- **Search** — full-text search across all pages with context snippets (debounced 300ms); supports multiple workspaces
- **Multi-workspace** — workspace picker in the header; switching workspaces reloads all content without a page refresh

## Architecture

```
Browser
  └── nginx (port 3000)
        ├── /* → React SPA (static files from dist/)
        └── /api/* → proxy → FastAPI (port 8000)
```

In development, `vite.config.ts` proxies `/api` to `http://localhost:8000`.

## Environment

The portal itself has no environment variables. All configuration lives on the API side:

| Variable | Default | Effect |
|----------|---------|--------|
| `PUBLIC_API_ENABLED` | `true` | Set to `false` on the API to disable all `/api/v1/public/*` endpoints (portal shows "Unable to connect") |

## Project Structure

```
portal/
├── src/
│   ├── api/
│   │   └── client.ts          # Typed fetch wrappers for all 6 public endpoints
│   ├── components/
│   │   ├── Layout.tsx          # Persistent header + sidebar shell
│   │   ├── PageViewer.tsx      # Markdown renderer (.prose design system)
│   │   └── SearchBar.tsx       # Debounced search with dropdown
│   ├── pages/
│   │   ├── WorkspaceHome.tsx   # Page list grouped by type
│   │   ├── PageView.tsx        # Full page with breadcrumb
│   │   └── SourcesView.tsx     # Sources table with drill-down
│   ├── index.css               # Design system (CSS variables, utilities)
│   └── main.tsx                # Routes
├── Dockerfile                  # Multi-stage: node:20-alpine build → nginx:alpine serve
├── nginx.conf                  # SPA fallback + /api proxy
└── vite.config.ts              # Dev proxy + build config
```

## Public API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/public/workspaces` | List workspaces |
| `GET /api/v1/public/workspaces/{id}/pages` | List pages (`page_type`, `limit`, `offset`) |
| `GET /api/v1/public/workspaces/{id}/pages/{path}` | Full page content |
| `GET /api/v1/public/workspaces/{id}/sources` | List sources (`status_filter`, `limit`, `offset`) |
| `GET /api/v1/public/workspaces/{id}/sources/{sid}/pages` | Pages from a source |
| `GET /api/v1/public/workspaces/{id}/search` | Search (`q`, `limit`) |

## Build

```bash
npm run build     # TypeScript check + Vite production bundle → dist/
npm run lint      # ESLint
```

The Docker image is built automatically by `make up` / `docker compose build portal`.
