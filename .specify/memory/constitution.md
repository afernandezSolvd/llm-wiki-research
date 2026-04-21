<!--
SYNC IMPACT REPORT
==================
Version change: template (0.0.0 / unpopulated) → 1.0.0

Modified principles (old → new):
  [PRINCIPLE_1_NAME] → I. LLM Wiki Pattern
  [PRINCIPLE_2_NAME] → II. Multi-Tenant Workspace Isolation
  [PRINCIPLE_3_NAME] → III. Async Worker Architecture
  [PRINCIPLE_4_NAME] → IV. Knowledge Quality Controls
  [PRINCIPLE_5_NAME] → V. Observability & Structured Logging
  (added)            → VI. Test Discipline

Added sections:
  - VI. Test Discipline (principle)
  - Technology Stack Constraints
  - Development Workflow

Removed sections:
  - [SECTION_2_NAME] / [SECTION_3_NAME] placeholders (replaced with concrete sections)

Templates requiring updates:
  ✅ .specify/templates/plan-template.md — Constitution Check gate compatible with
     the six principles defined here; no structural changes required.
  ✅ .specify/templates/spec-template.md — Scope/requirements structure aligns with
     multi-tenant, quality-gated requirements; no structural changes required.
  ✅ .specify/templates/tasks-template.md — Phase/story structure supports async
     worker and test-discipline principles; no structural changes required.

Follow-up TODOs:
  None — all placeholders resolved. No deferred items.
-->

# Context — LLM-Maintained Wiki System Constitution

## Core Principles

### I. LLM Wiki Pattern

This system MUST maintain structured Markdown wiki pages as the primary knowledge
layer — not raw document retrieval. Every ingest operation MUST produce curated,
deduplicated wiki pages committed to git with full citation back to source chunks.
Raw RAG over source documents is explicitly prohibited as a query strategy; queries
MUST read from wiki pages and knowledge graph nodes, not raw source text.

**Rationale**: Wiki pages are compact, authoritative, and deduplicated. A single
`company-x.md` page beats fifty chunked PDFs for consistency, context efficiency,
and maintainability. This is the core differentiator of this system.

### II. Multi-Tenant Workspace Isolation

Every workspace MUST be fully isolated: its own git repository under `wiki_repos/`,
its own scoped role assignments (reader/editor/admin), and its own schema definition.
Cross-workspace data access is forbidden at the application layer.

Role escalation MUST follow the strict hierarchy: `reader (1) < editor (2) < admin
(3) < platform_admin`. A `platform_admin` flag bypasses workspace membership — it
MUST be granted only to infrastructure operators, never to end users.

**Rationale**: Multi-team deployments require hard isolation guarantees. A bug in
one team's ingest pipeline MUST NOT corrupt another team's wiki.

### III. Async Worker Architecture

All Celery task functions MUST be synchronous (`def`, not `async def`) and delegate
async work via the `_run(coro)` helper, which calls `asyncio.run()`. Using
`asyncio.get_event_loop()` anywhere in worker code is forbidden.

All `app.*` imports inside worker modules MUST be placed inside the async helper
function, not at module level, to prevent circular imports at worker startup.

Worker task names MUST match the module path exactly:
`name="app.workers.{module}.{function}"`.

Retry limits: ingest `max_retries=3`, lint `max_retries=2`. Before re-raising any
exception, workers MUST call `_mark_job_failed` / `_mark_run_failed`.

**Rationale**: Celery tasks run in threads, not an async event loop. Violating this
boundary causes subtle concurrency bugs that are extremely hard to diagnose.

### IV. Knowledge Quality Controls

Every proposed wiki page edit MUST pass through the hallucination gate
(`claude-haiku-4-5`) before being committed to git, unless `HALLUCINATION_GATE_ENABLED`
is explicitly set to `false` in a local development environment.

The `original_embedding` field on `wiki_pages` is set at creation and MUST NEVER be
updated — it is the immutable drift anchor. Semantic drift MUST be monitored
continuously using cosine distance from this anchor. Pages exceeding the configured
`DRIFT_ALERT_THRESHOLD` (default `0.35`) MUST be surfaced as warnings; pages exceeding
`threshold × 2` MUST be flagged as errors.

Lint runs (contradiction detection, orphan page checks, drift scans) MUST be scheduled
at least weekly via Celery Beat for every active workspace.

**Rationale**: LLM-generated content can silently hallucinate or drift. The gate and
drift monitoring are the trust layer that makes this system enterprise-usable.

### V. Observability & Structured Logging

All log statements MUST use structured key-value format:
`logger.info("event_name", key=value)`. F-string log messages are forbidden.

Every background worker MUST emit structured events at task start, task completion,
and task failure. Worker health MUST be visible via the Flower dashboard at all times.

Prompt caching (`cache_control: ephemeral`) MUST be applied to the top-N hot wiki
pages in the system prompt to reduce latency and API cost for high-traffic workspaces.

**Rationale**: Structured logs enable downstream alerting and analytics without
post-processing. Prompt caching is a correctness-adjacent concern — without it,
latency degrades unpredictably under load.

### VI. Test Discipline

Unit tests (`tests/unit/`) MUST NOT import `AsyncSessionLocal`, `get_redis_pool`, or
any external service. External boundaries are mocked at the function boundary only.

Integration tests (`tests/integration/`) MUST run against a real PostgreSQL instance.
`_cosine_distance` MUST NEVER be mocked — it MUST be tested with real vectors.

Every new worker MUST have at least one unit test covering its pure utility functions.
Test file names MUST mirror source paths:
`app/workers/ingest_worker.py` → `tests/unit/test_ingest_worker.py`.

Async test functions MUST be decorated with `pytest.mark.asyncio`.

**Rationale**: Mock-first testing produced false confidence in the past; real-DB
integration tests catch schema and query bugs that unit tests cannot.

## Technology Stack Constraints

The following technologies are non-negotiable for core system services. Substitutions
require a constitution amendment.

| Layer | Locked Technology |
|---|---|
| API framework | FastAPI + SQLAlchemy 2.0 async, Python 3.12 |
| Database | PostgreSQL 16 + pgvector, HNSW indexes, 1024-dim Voyage embeddings |
| Cache / Queue | Redis 7, Celery 5 |
| LLM (ingest/lint) | Anthropic `claude-opus-4-6` |
| LLM (gate) | Anthropic `claude-haiku-4-5-20251001` |
| Embeddings | Voyage AI `voyage-3-large` (1024 dimensions) |
| Wiki storage | Git via gitpython, one repo per workspace |

Vector columns MUST use `Vector(1024)` — always 1024 dimensions to match
`voyage-3-large`. HNSW indexes MUST specify `m=16, ef_construction=64` with
`vector_cosine_ops`.

All prompt templates MUST use `${var}` placeholders replaced via `.replace()`, NOT
Python `.format()`. Source content contains literal `{}` characters.

`get_redis_pool()` returns synchronously via `lru_cache` — it MUST NEVER be awaited.

## Development Workflow

### Database Migrations

After changing any model in `app/models/`, a new Alembic revision MUST be created:
`alembic revision --autogenerate -m "description"`.

Existing migration files MUST NEVER be edited — create new revisions instead.
Every migration's `downgrade()` MUST symmetrically reverse its `upgrade()`.
Autogenerated migrations MUST be reviewed before applying — autogenerate misses
`server_default` changes and some index types.

### API & Code Conventions

- All database work MUST occur inside `async with AsyncSessionLocal() as db:`.
- Async everywhere in `app/` code; sync only at the Celery task boundary.
- The three core operations (ingest, query, lint) are the only permitted entry
  points for mutating wiki state. Direct database writes that bypass these
  workflows are forbidden outside of migration scripts.

### Multi-Repo and Multi-Engineer Collaboration

This codebase is intended as a demonstration of the LLM Wiki pattern for teams
spanning multiple repositories and engineers. Each team or product domain SHOULD
operate its own workspace. The hallucination gate and drift monitoring are the
shared quality floor that all workspaces inherit — they MUST NOT be disabled in
shared or production environments.

Feature branches MUST pass `make lint` (ruff + mypy) and `make test` before merging.
Coverage reports MUST be generated with `pytest --cov=app --cov-report=html`.

## Governance

This constitution supersedes all other informal practices. Amendments MUST be
documented with a version bump, a rationale, and (where applicable) a migration
plan for any code that relied on the superseded rule.

**Version policy** (semantic versioning):
- MAJOR: Backward-incompatible governance change, principle removal, or principle
  redefinition that invalidates existing implementations.
- MINOR: New principle or section added, or materially expanded guidance.
- PATCH: Clarifications, wording fixes, non-semantic refinements.

**Amendment procedure**: Open a PR updating this file. The PR description MUST
include the bump type, rationale, and list of dependent files updated. All active
engineers on the project MUST review constitution amendments before merge.

**Compliance review**: Every PR that touches worker code, migration files, or
prompt templates MUST include a Constitution Check comment confirming compliance
with Principles III, IV, and VI respectively. Use `.specify/templates/plan-template.md`
Constitution Check gates as the reference checklist.

**Version**: 1.0.0 | **Ratified**: 2026-04-21 | **Last Amended**: 2026-04-21
