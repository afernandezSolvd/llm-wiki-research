# Tasks: Consistency Lint

**Input**: Design documents from `/specs/005-consistency-lint/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Organization**: Tasks grouped by user story. No new tables, no new endpoints, no new dependencies — all changes extend existing files.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

**Purpose**: Verify clean baseline before touching production files.

- [x] T001 Run `make test` inside Docker (`docker compose exec api python3 -m pytest tests/unit/ -v`) and confirm all existing tests pass as baseline

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the unit test file so constitution-required tests can be written alongside implementation.

⚠️ **CRITICAL**: T002 must complete before any US1/US2/US3 implementation begins to keep tests in sync with code.

- [x] T002 Create `tests/unit/test_consistency_lint.py` with import skeleton: import `parse_lint_response` from `app.llm.output_parsers.lint_findings` and add three empty placeholder test functions (`test_parse_consistency_type`, `test_evidence_builder_structure`, `test_parse_topic_field`) — each raises `NotImplementedError` so they fail until implemented

**Checkpoint**: Baseline green + test file exists → implementation phases can begin

---

## Phase 3: User Story 1 — Detect Contradictions Across Pages (Priority: P1) 🎯 MVP

**Goal**: Rename finding type from "contradiction" to "consistency" and extend Phase 3 of the lint worker to catch contradictions in pages outside KG communities using embedding similarity.

**Independent Test**: Trigger a lint run on a workspace with two pages having conflicting port numbers → findings API returns a finding with `finding_type: "consistency"` and `severity: "error"`.

- [x] T003 [US1] Update `app/llm/prompts/lint.py` — change `"type": "contradiction"` to `"type": "consistency"` in `LINT_SYSTEM`; add `"topic"` field to the JSON schema comment (a short label for the entity/claim being contradicted, e.g. `"topic": "Redis port"`)
- [x] T004 [US1] Add embedding-similarity candidate pairing to `app/workers/lint_worker.py` Phase 3: after building `page_pairs` from KG communities (existing), for each page with no `community_id` KG node, query pgvector for top-3 nearest neighbors using `ORDER BY embedding <=> :ref_embedding LIMIT 3` (SQLAlchemy `text()` with bindparams); add these pairs to `page_pairs`, capped at 30 new pairs total from this path; skip pairs already covered by KG communities
- [x] T005 [US1] In `app/workers/lint_worker.py`, raise the total LLM call cap from `page_pairs[:50]` to `page_pairs[:100]`; prioritize KG community pairs first (up to 70), then embedding-similarity pairs (up to 30); add a structured log event `"lint_phase3_pairs_built"` with `community_pairs`, `embedding_pairs`, `total_pairs` counts

**Checkpoint**: A full lint run now detects "consistency" findings for both KG-community pages and non-KG pages

---

## Phase 4: User Story 2 — Rich Finding Evidence for Navigation (Priority: P2)

**Goal**: Each consistency finding carries enough context (page paths + conflicting excerpts + topic label) for an operator to navigate directly to the offending pages without any secondary search.

**Independent Test**: Fetch findings for a lint run that produced consistency findings → each finding's `evidence` JSON contains `conflicting_pages` (list of `{path, excerpt}`), `topic`, and `pair_source`.

- [x] T006 [US2] Update `app/llm/output_parsers/lint_findings.py` — add `topic: str = ""` field to `LLMLintFinding` dataclass; parse `item.get("topic", "")` in `parse_lint_response`
- [x] T007 [US2] Update evidence construction in `app/workers/lint_worker.py` — replace the `evidence` dict in the `LintFinding(...)` call with the new schema: `{"conflicting_pages": [{"path": page_a.page_path, "excerpt": f.page_a_excerpt}, {"path": page_b.page_path, "excerpt": f.page_b_excerpt}], "topic": f.topic, "pair_source": "kg_community"}` for community pairs and `"pair_source": "embedding_similarity"` for embedding pairs; also keep `page_a`, `page_b`, `page_a_excerpt`, `page_b_excerpt` keys for backward compatibility

**Checkpoint**: Findings returned by the API include navigable page refs, excerpts, and a topic label

---

## Phase 5: User Story 3 — Auto-Trigger After Ingest (Priority: P3)

**Goal**: After a source ingest completes, a consistency lint pass for the affected workspace is enqueued automatically — no manual trigger required.

**Independent Test**: Upload a source, trigger ingest, wait for completion → a new `LintRun` with `scope="incremental"` appears in the jobs list without any manual lint API call.

- [x] T008 [US3] In `app/workers/ingest_worker.py`, at the end of `_process_ingest_job_async` (after the `maybe_rebuild_communities.apply_async` call), add: create a `LintRun` record with `workspace_id=workspace_id`, `scope="incremental"`, `page_ids_scoped=[list of WikiPage IDs written or updated during this job]`; `await db.commit()`; then dispatch `run_lint_pass.apply_async(args=[str(lint_run.id)], queue="lint")`; wrap in try/except so lint failure never rolls back or fails the ingest job; import `LintRun` and `run_lint_pass` inside the async helper (lazy import per constitution rule)

**Checkpoint**: Every completed ingest automatically produces a follow-up incremental lint run

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Constitution compliance — unit tests, type checking, full test suite.

- [x] T009 [P] Implement `test_parse_consistency_type` in `tests/unit/test_consistency_lint.py`: call `parse_lint_response` with a JSON string containing `"type": "consistency"`, `"severity": "error"`, `"description": "..."`, `"page_a_excerpt": "..."`, `"page_b_excerpt": "..."`, `"topic": "Redis port"` → assert `finding.finding_type == "consistency"` and `finding.topic == "Redis port"`
- [x] T010 [P] Implement `test_parse_topic_field` in `tests/unit/test_consistency_lint.py`: call `parse_lint_response` with a JSON string missing the `"topic"` key → assert `finding.topic == ""` (graceful default)
- [x] T011 [P] Implement `test_evidence_builder_structure` in `tests/unit/test_consistency_lint.py`: construct a `LLMLintFinding` with `topic="Redis port"`, `page_a_excerpt="port 6379"`, `page_b_excerpt="port 6380"`, and assert that when used to build the evidence dict (inline dict construction matching the pattern in lint_worker.py) the result contains `"conflicting_pages"` as a list of length 2 and `"topic": "Redis port"`
- [x] T012 Run `docker compose exec api python3 -m pytest tests/unit/ -v` and confirm all tests pass (including the 3 new ones from T009–T011)
- [x] T013 Run `make lint` (`ruff check app/ tests/` + `mypy app/`) and fix any type annotation issues in the changed files

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: After Phase 1
- **US1 (Phase 3)**: After Phase 2 — T003 before T004, T004 before T005
- **US2 (Phase 4)**: After Phase 3 (T003 must be done before T006 since T006 adds the `topic` field the prompt now produces)
- **US3 (Phase 5)**: After Phase 2 — independent of US1/US2 (different file)
- **Polish (Phase 6)**: After US1, US2, US3 complete

### User Story Dependencies

- **US1 (P1)**: Unblocked after Phase 2 — MVP, deliver first
- **US2 (P2)**: Depends on T003 (prompt must output `topic` before parser can consume it)
- **US3 (P3)**: Independent of US1/US2 — can run in parallel with Phase 3/4

### Parallel Opportunities

- T003, T004, T005 are sequential (same file section, logical dependency)
- T006 and T007 are sequential (T006 adds the dataclass field T007 uses)
- **T008 can start in parallel with T003** — different file (`ingest_worker.py` vs `lint_worker.py`)
- T009, T010, T011 are all parallel (same test file, different test functions)

---

## Parallel Example: US3 and US1 together

```bash
# These can run concurrently — completely different files:
Task T003: "Update app/llm/prompts/lint.py"
Task T008: "Add lint trigger to app/workers/ingest_worker.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: baseline check
2. Complete Phase 2: create test file
3. Complete Phase 3 (T003–T005): rename type + improve detection coverage
4. **STOP and VALIDATE**: trigger lint manually, verify `finding_type: "consistency"` appears
5. Deploy MVP

### Incremental Delivery

1. Setup + Foundational → baseline confirmed
2. US1 (T003–T005) → contradiction detection works with "consistency" type + embedding pairs
3. US2 (T006–T007) → findings gain rich evidence for navigation
4. US3 (T008) → auto-trigger closes the feedback loop
5. Polish (T009–T013) → tests green, linter clean

### Parallel Strategy (if working across 2 tracks)

- Track A: US1 (T003→T004→T005) then US2 (T006→T007)
- Track B: US3 (T008) immediately after Phase 2

---

## Notes

- No migrations: `LintFinding.finding_type` is an unconstrained String(30); no ALTER TABLE needed
- Backward compat: keep `page_a`/`page_b` keys in evidence alongside the new `conflicting_pages` list
- All imports inside async helpers per constitution Principle III
- `run_lint_pass` import in ingest_worker must be lazy (inside async function, not module level)
- Embedding similarity query uses `text()` with `bindparams` — same pattern already used in `public.py` search
