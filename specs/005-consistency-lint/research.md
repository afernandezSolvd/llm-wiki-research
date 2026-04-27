# Research: Consistency Lint

**Branch**: `005-consistency-lint` | **Date**: 2026-04-27

## Finding 1: Contradiction Detection Already Exists (Phase 3 of lint_worker.py)

**Decision**: Extend and harden the existing Phase 3 — do not build from scratch.

**Rationale**: `app/workers/lint_worker.py` already has Phase 3 LLM contradiction detection (lines 166–238). It uses KG community membership as candidate pairs, calls `claude-opus-4-6` per pair, and stores findings with type "contradiction" + `evidence` JSONB containing `page_a`, `page_b`, `page_a_excerpt`, `page_b_excerpt`. The `LintFinding.finding_type` is a `String(30)` with no enum constraint — adding a new value requires no schema migration.

**Alternatives considered**:
- Build a standalone consistency worker — rejected, the lint lifecycle (LintRun, LintFinding, findings API, quality dashboard) is already the right container.
- Use a separate "consistency" table — rejected, `LintFinding.evidence` JSONB handles multi-page references without a schema change.

---

## Finding 2: Coverage Gap — Pages Outside KG Communities Are Skipped

**Decision**: Add embedding-similarity-based pairing as a fallback for pages with no KG community assignment.

**Rationale**: Phase 3 only iterates `community_to_pages` — pages without a `KGNode` or without a `community_id` are never checked. This is a significant blind spot for small workspaces or newly ingested pages that haven't yet been through community detection. pgvector supports `ORDER BY embedding <=> :ref_embedding LIMIT 5` natively — no extra dependency needed.

**Alternatives considered**:
- All-pairs comparison (O(N²)) — rejected, too expensive for large workspaces. Embedding similarity produces semantically relevant pairs at O(N) per page.
- Run community detection before every lint pass — rejected, community rebuild is its own debounced Celery task and should not be forced inline.

---

## Finding 3: Finding Type Naming — "contradiction" vs "consistency"

**Decision**: Rename the LLM output type from `"contradiction"` to `"consistency"` by updating `LINT_SYSTEM` in `app/llm/prompts/lint.py`.

**Rationale**: The spec defines a new finding type "consistency". The current prompt hard-codes `"type": "contradiction"`. Aligning the type name with the spec makes the quality dashboard and findings API output match operator expectations. No schema change needed — `finding_type` is a free-text String(30).

**Alternatives considered**:
- Keep `"contradiction"` and add a display alias — rejected, unnecessary indirection with no benefit.

---

## Finding 4: Auto-Trigger Lint After Ingest

**Decision**: After ingest completes in `_process_ingest_job_async`, create a `LintRun` record with `scope="incremental"` and `page_ids_scoped` set to the pages touched by the ingest, then dispatch `run_lint_pass.apply_async`.

**Rationale**: The ingest worker already dispatches `maybe_rebuild_communities.apply_async` and `push_to_remote.apply_async` after completion (lines 439, 298). Adding a lint dispatch follows the exact same pattern and requires no architectural changes. Using `scope="incremental"` with the touched page IDs limits the lint pass to only the changed pages, keeping it fast.

**Alternatives considered**:
- Trigger a full workspace lint — rejected, too slow for every ingest. Incremental scoped lint is sufficient to catch contradictions introduced by the new content.
- Use Celery beat to schedule more frequent lint runs instead — rejected, beat cadence is weekly by default and cannot react to specific ingests.

---

## Finding 5: Multi-Page Finding Support

**Decision**: Extend `evidence` JSONB schema to support N pages under a `"conflicting_pages"` key: `[{"path": "...", "excerpt": "..."}]`. Keep backward-compatible by also populating `page_a` / `page_b` for two-page findings.

**Rationale**: The existing `LintFinding.evidence` JSONB is schema-free. The current structure (`page_a`, `page_b`, `page_a_excerpt`, `page_b_excerpt`) handles the two-page case but not three or more. Adding a `conflicting_pages` list covers both cases. No migration required.

**Alternatives considered**:
- Add a `LintFindingPage` join table — rejected, overkill for this use case. JSONB is the right tool for ad-hoc structured metadata.

---

## Finding 6: LLM Cap Strategy

**Decision**: Keep a total cap of 100 LLM calls per lint run (up from 50), split across community pairs (primary) and embedding-similarity pairs (secondary, capped at 5 nearest neighbors per page, max 30 calls total from this path).

**Rationale**: The 50-call cap in the current implementation is low for larger workspaces. Embedding-similarity pairs are pre-filtered by semantic relevance so false-positive rates are low. 100 total calls at ~500 tokens each = ~50K tokens per lint run, well within acceptable cost for a weekly-or-less-frequent operation.

**Alternatives considered**:
- Unlimited calls — rejected, unbounded cost in large workspaces.
- Batching multiple page pairs into one LLM call — deferred, possible future optimization but adds prompt complexity.
