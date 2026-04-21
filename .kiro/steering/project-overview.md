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

## Entry Points
- API: app/main.py → app/api/router.py → app/api/v1/*.py
- Workers: app/workers/{ingest,lint,embedding,graph}_worker.py
- Models: app/models/*.py
- Config: app/config.py (Pydantic Settings, reads from .env)

## Development
- `make up` starts everything via docker-compose
- `make migrate` runs alembic upgrade head
- `make test` runs pytest with coverage
- API docs: http://localhost:8000/docs
- Worker dashboard: http://localhost:5555 (Flower)
