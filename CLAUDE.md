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
- Python 3.12 (backend, existing), HTML5/ES2022 (frontend, + FastAPI + SQLAlchemy 2.0 async (existing), Celery 5 (001-status-web-gui)
- PostgreSQL 16 via existing models; Redis 7 for queue depth (LLEN) (001-status-web-gui)

## Recent Changes
- 001-status-web-gui: Added Python 3.12 (backend, existing), HTML5/ES2022 (frontend, + FastAPI + SQLAlchemy 2.0 async (existing), Celery 5
