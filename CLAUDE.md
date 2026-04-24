# Context Wiki System — Claude Code Instructions

## What This Project Is
An LLM-maintained wiki API. Sources (PDFs, URLs, text) are ingested into
structured Markdown wiki pages via Celery workers. Pages are stored in git
and PostgreSQL. Claude (claude-opus-4-6) does the actual writing.

## Stack
- FastAPI + SQLAlchemy 2.0 async (Python 3.12)
- PostgreSQL 16 + pgvector (HNSW indexes, 1024-dim Voyage embeddings)
- Celery 5 with Redis broker — queues: ingest, lint, embedding, graph
- Anthropic API (claude-opus-4-6 for ingest/lint, haiku-4-5 for gate)
- Voyage AI (voyage-3-large) for embeddings — separate key from Anthropic
- Git (gitpython) — one repo per workspace under ./wiki_repos/

## Development Commands
- `make up` — start full stack (PostgreSQL, Redis, API, workers, beat, flower)
- `make down` — stop everything
- `make migrate` — run alembic upgrade head
- `make test` — pytest with coverage
- `make lint` — ruff + mypy
- `make dev` — uvicorn with hot-reload (no workers)

## Key Architecture Rules
- Workers use `asyncio.run()` NOT `asyncio.get_event_loop()` — Celery tasks
  run in threads, not async context
- All prompt templates use `${var}` placeholders replaced via `.replace()`,
  NOT Python `.format()` — source content contains literal `{}` characters
- `original_embedding` on wiki_pages is set at creation and NEVER updated —
  it is the absolute drift anchor
- `get_redis_pool()` returns synchronously (lru_cache) — never `await` it
- Voyage AI and Anthropic are separate services with separate API keys

## Testing
- Unit tests: `tests/unit/` — no DB, no external services
- Integration tests: `tests/integration/` — requires running PostgreSQL
- Run specific test: `pytest tests/unit/test_drift.py -v`
- Coverage report: `pytest --cov=app --cov-report=html`

## Migrations
- After changing models in `app/models/`, always create a migration:
  `alembic revision --autogenerate -m "description"`
- Never edit existing migration files — always create new ones

## Code Conventions
- Async everywhere in app code; sync only at Celery task boundary
- All DB work inside `async with AsyncSessionLocal() as db:`
- Imports inside async functions (lazy loading) to avoid circular imports
  in worker files
- Structured logging: `logger.info("event_name", key=value)` — never
  f-string log messages

## Active Technologies
- Python 3.12, FastAPI, SQLAlchemy 2.0 async (backend)
- Node.js 20, TypeScript, Vite, React (portal frontend — `portal/`)
- PostgreSQL 16 + pgvector, Redis 7 (data layer)
- Python 3.12 + FastAPI `>=0.111.0`, `mcp>=1.25,<2` (FastMCP included), SQLAlchemy 2.0 async (existing) (003-improve-mcp-server)
- PostgreSQL 16 + pgvector (existing, no schema changes) (003-improve-mcp-server)
- Python 3.12 (existing) + gitpython (existing), httpx or urllib.request for provider API calls (no new SDK), redis-py (existing, for push serialization lock) (004-obsidian-git-sync)
- PostgreSQL 16 — three new nullable columns on `workspaces` table; Redis — distributed lock key per workspace (004-obsidian-git-sync)

## Recent Changes
- Added read-only portal (`portal/`) — Vite + React SPA at port 3000
- Added public API router (`app/api/v1/public.py`) — 6 unauthenticated endpoints under `/api/v1/public/`, guarded by `PUBLIC_API_ENABLED` env var
- Added status dashboard — HTML/ES2022 frontend showing ingest queue health
