# Context Wiki System — Project Overview

## What This Is
An enterprise LLM-maintained wiki API. Sources (PDFs, URLs, text files) are
ingested by Celery workers that call the Anthropic API (claude-opus-4-6) to
write and update Markdown wiki pages. Pages live in per-workspace git repos
backed by PostgreSQL with pgvector for semantic search.

## Core Operations
- **Ingest**: source file → LLM → wiki page edits + KG entities
- **Query**: question → hybrid retrieval (vector + graph) → LLM → answer with citations
- **Lint**: wiki → structural checks + semantic drift detection + contradiction scan

## Stack
- Python 3.12, FastAPI, SQLAlchemy 2.0 async, asyncpg
- PostgreSQL 16 + pgvector (HNSW indexes, cosine distance)
- Celery 5 + Redis (queues: ingest, lint, embedding, graph)
- Anthropic API (claude-opus-4-6 for ingest/lint, haiku-4-5 for hallucination gate)
- Voyage AI (voyage-3-large, 1024-dim) for embeddings — separate from Anthropic
- gitpython (one git repo per workspace under ./wiki_repos/)
- NetworkX + Louvain (knowledge graph community detection)
- Node.js 20 / TypeScript / Vite / React — portal SPA (`portal/`)

## Entry Points
- API: `app/main.py` → `app/api/router.py` → `app/api/v1/*.py`
- Public API (no auth): `app/api/v1/public.py` — 6 read-only endpoints under `/api/v1/public/`
- Workers: `app/workers/{ingest,lint,embedding,graph}_worker.py`
- Models: `app/models/*.py`
- Config: `app/config.py` (Pydantic Settings, reads from `.env`)
- Portal: `portal/src/main.tsx` → `portal/src/components/Layout.tsx`
- MCP server: `app/mcp/server.py` (FastMCP, 13 tools) — stdio via `.claude/mcp-context-wiki.sh`, HTTP at `POST /mcp`

## MCP Tools (13 purpose-built)
- `list_workspaces`, `get_workspace_status` — workspace discovery
- `ingest_url`, `ingest_file`, `get_ingest_status` — source ingestion
- `query_wiki` — hybrid retrieval (vector + KG) + LLM answer with citations
- `list_wiki_pages`, `get_wiki_page`, `create_wiki_page`, `update_wiki_page` — wiki CRUD
- `list_sources` — source listing
- `trigger_lint` — quality/drift checks
- `search_tools` — on-demand tool schema lookup

## MCP Setup
- **Claude Code**: stdio via `.claude/mcp-context-wiki.sh` → `docker compose exec -T api python -m app.mcp.server`
- **Kiro**: HTTP via auth proxy at `http://localhost:8001/mcp` (token auto-managed) or direct at `http://localhost:8000/mcp` with `Authorization: Bearer <token>`
- Auth proxy (`tools/mcp_auth_proxy.py`) runs at `:8001`, auto-refreshes tokens from `/api/v1/status/bootstrap`

## Development
- `make up` starts everything via docker-compose
- `make migrate` runs alembic upgrade head
- `make test` runs pytest with coverage
- API docs: http://localhost:8000/docs
- Portal (read-only wiki browser): http://localhost:3000
- Worker dashboard: http://localhost:5555 (Flower)
- Portal dev server: `cd portal && npm run dev` → http://localhost:5173
