# Implementation Plan: Consistency Lint

**Branch**: `005-consistency-lint` | **Date**: 2026-04-27 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/005-consistency-lint/spec.md`

## Summary

Harden the existing Phase 3 LLM contradiction detection in the lint worker by: (1) renaming the finding type from "contradiction" to "consistency", (2) adding embedding-similarity-based candidate pairing for pages outside KG communities, (3) extending the evidence schema to support N-page contradictions, and (4) auto-triggering an incremental lint pass after every ingest. No new tables, no new endpoints, no new dependencies.

## Technical Context

**Language/Version**: Python 3.12 (existing)
**Primary Dependencies**: FastAPI, SQLAlchemy 2.0 async, Celery 5, gitpython, redis-py, anthropic SDK (all existing — no new dependencies)
**Storage**: PostgreSQL 16 + pgvector (existing — no schema changes), Redis 7 (existing)
**Testing**: pytest + pytest-asyncio (existing)
**Target Platform**: Linux Docker container (existing)
**Project Type**: Web service + async worker (existing)
**Performance Goals**: Consistency lint pass over 200 pages completes within a single lint run's existing time budget; total LLM calls capped at 100 per run
**Constraints**: No new tables; no new API endpoints; no new Python packages; worker code must remain sync-def + asyncio.run() per constitution
**Scale/Scope**: Per-workspace lint; up to 200 pages; ~100 LLM pair comparisons per run

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I. LLM Wiki Pattern | ✓ PASS | Lint reads wiki pages only; no raw source access |
| II. Workspace Isolation | ✓ PASS | All queries scoped to `workspace_id`; no cross-workspace comparison |
| III. Async Worker Architecture | ✓ PASS | lint_worker.py already sync-def + asyncio.run(); changes follow same pattern |
| IV. Knowledge Quality Controls | ✓ PASS | This feature IS a quality control; hallucination gate unaffected |
| V. Observability | ✓ PASS | All new log statements use structured key=value format |
| VI. Test Discipline | ✓ PASS | Unit tests required for new pure utility functions (candidate pairing logic, evidence builder) |

No gate violations.

## Project Structure

### Documentation (this feature)

```text
specs/005-consistency-lint/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/
│   └── findings-api.md  ← Phase 1 output
└── tasks.md             ← Phase 2 output (via /speckit.tasks)
```

### Source Code (changed files only — no new files except test)

```text
app/
├── llm/
│   ├── prompts/
│   │   └── lint.py                         ← rename type "contradiction"→"consistency"; add topic field
│   └── output_parsers/
│       └── lint_findings.py                ← parse "topic" field; build conflicting_pages list
├── workers/
│   ├── lint_worker.py                      ← Phase 3: add embedding-similarity pairs, raise cap to 100, new evidence schema
│   └── ingest_worker.py                    ← add incremental lint trigger after ingest completes
└── (no new API files — existing findings endpoint already handles the new type)

tests/
└── unit/
    └── test_consistency_lint.py            ← NEW: unit tests for candidate pairing, evidence builder, parser
```

**Structure Decision**: Single-project extension. All changes are confined to the existing lint + ingest workers and their supporting LLM modules. No new tables, routers, or workers.

## Complexity Tracking

No constitution violations. No complexity justification required.
