# Feature Specification: Consistency Lint

**Feature Branch**: `005-consistency-lint`
**Created**: 2026-04-27
**Status**: Draft
**Input**: User description: "we need consistency lint to look for contradictory information to avoid adding noise in the knowledge base"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Detect Contradictions Across Pages (Priority: P1)

An operator triggers a lint run (manually or via the scheduled beat task) and the system automatically scans wiki pages for contradictory factual claims about the same entity or concept — e.g., two pages that disagree on a port number, a version, a status flag, or a relationship. Contradictions are surfaced as new lint findings with severity "error" alongside existing lint finding types.

**Why this priority**: Without this, the knowledge base accumulates conflicting facts silently. Every ingest that updates one page without updating related pages leaves orphaned contradictions. This is the core value of the feature.

**Independent Test**: Can be fully tested by ingesting two sources with known conflicting facts about the same entity, triggering a lint run, and verifying that a consistency finding is created pointing to both conflicting pages.

**Acceptance Scenarios**:

1. **Given** two wiki pages that state conflicting values for the same factual claim (e.g., page A says "Redis runs on port 6379", page B says "Redis runs on port 6380"), **When** a lint run is triggered, **Then** a consistency finding is created with severity "error" referencing both pages and quoting the conflicting claims.
2. **Given** all wiki pages have internally consistent facts, **When** a lint run is triggered, **Then** no consistency findings are produced.
3. **Given** a lint run completes, **When** the operator fetches findings, **Then** consistency findings are included in the results alongside existing finding types (hallucination, drift, etc.).

---

### User Story 2 - Review and Navigate Consistency Findings (Priority: P2)

An operator reviewing the knowledge base quality dashboard sees consistency findings grouped by entity, can understand exactly which two (or more) pages disagree, sees the conflicting text excerpts side by side, and navigates directly to each offending page to resolve the conflict manually.

**Why this priority**: Detection alone is not enough — operators need enough context in the finding to act on it without hunting through the wiki themselves.

**Independent Test**: Can be tested by querying the findings API for a lint run that produced consistency findings and verifying the finding payload includes page references, conflicting excerpts, and the entity/claim at the center of the contradiction.

**Acceptance Scenarios**:

1. **Given** a lint run with consistency findings, **When** the operator fetches findings for that run, **Then** each finding includes: the conflicting page paths, a short excerpt from each page showing the contradictory claim, and the entity/topic the contradiction is about.
2. **Given** the operator wants to fix a contradiction, **When** they navigate to either referenced page path, **Then** they can read the full page and edit it to resolve the conflict.

---

### User Story 3 - Consistency Check Triggered Automatically After Ingest (Priority: P3)

After a source is ingested and wiki pages are written or updated, the system automatically enqueues a consistency lint pass for the affected pages so contradictions introduced by the new content are caught promptly without requiring a manual lint trigger.

**Why this priority**: Ingesting new content is the primary way contradictions enter the knowledge base. Tying the consistency check to the ingest lifecycle closes the feedback loop automatically.

**Independent Test**: Can be tested by uploading a source with a fact that contradicts an existing page, waiting for ingest to complete, and verifying a consistency finding appears without any manual lint trigger.

**Acceptance Scenarios**:

1. **Given** a source is ingested that creates or updates a wiki page, **When** ingest completes, **Then** a consistency lint pass is automatically triggered for the workspace.
2. **Given** the auto-triggered consistency lint finds no contradictions, **Then** no findings are created and the ingest job is considered fully successful.

---

### Edge Cases

- What if the same contradictory claim appears across more than two pages? The finding should reference all pages involved, not just the first pair found.
- What if two pages state the same fact in different phrasings but with the same meaning? The system must not flag stylistic or synonym-level differences as contradictions.
- What if a page is deleted while a consistency lint run is in progress? The finding for that page should be skipped or discarded.
- What if the workspace has hundreds of pages — does the check complete in reasonable time? The pass must run asynchronously and not block the ingest queue.
- What happens when more than two pages disagree on the same value? All conflicting pages should be grouped into a single finding, not one finding per pair.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The lint system MUST support a new finding type "consistency" distinct from existing finding types (hallucination, drift, format).
- **FR-002**: When a consistency lint pass runs, the system MUST compare factual claims across all wiki pages in the same workspace and identify claims that directly contradict each other.
- **FR-003**: Each consistency finding MUST include: finding type ("consistency"), severity ("error"), paths of all involved pages, and a short excerpt from each page showing the contradictory text.
- **FR-004**: Consistency lint MUST be triggerable on demand via the existing lint trigger endpoint with no changes to the trigger API surface.
- **FR-005**: Consistency lint MUST also run automatically as part of the existing scheduled periodic lint task.
- **FR-006**: After a source ingest completes, the system MUST enqueue a consistency lint pass for the affected workspace.
- **FR-007**: Consistency findings MUST be retrievable via the existing findings API alongside other finding types — no new retrieval endpoint is required.
- **FR-008**: The consistency check MUST run asynchronously and MUST NOT block the ingest worker or the API response.
- **FR-009**: If no contradictions are found, the lint run MUST complete successfully with zero consistency findings.
- **FR-010**: The system MUST NOT flag differences in phrasing, tone, level of detail, or synonymous expressions as contradictions — only mutually exclusive factual claims (conflicting numbers, boolean states, proper names, explicit opposing assertions).

### Key Entities

- **ConsistencyFinding**: A lint finding of type "consistency" that references two or more pages with conflicting factual claims, including excerpts and the entity/topic at the center of the contradiction.
- **LintRun**: Existing entity — extended to include consistency check results alongside existing finding categories.
- **WikiPage**: Existing entity — each page is a source of factual claims to be compared against all other pages in the workspace.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of direct factual contradictions between wiki pages (conflicting numeric values, status flags, proper names for the same entity) are surfaced as findings within one lint run after the conflict is introduced.
- **SC-002**: Zero false positives for pages that express the same fact in different words or at different levels of detail (paraphrase tolerance validated by a test suite of known-equivalent statements).
- **SC-003**: A consistency lint pass over a workspace with up to 200 pages completes within the time budget of an existing lint run with no noticeable slowdown for operators.
- **SC-004**: Operators can identify and navigate to all conflicting pages from a single finding record with no secondary search required.
- **SC-005**: Contradictions introduced by new ingests are detected automatically within one scheduled lint cycle without requiring a manual trigger.

## Assumptions

- The existing lint finding schema is flexible enough to accommodate a new "consistency" finding type without a breaking schema change.
- The current lint runner already processes pages within a workspace in a single task context, making cross-page comparison feasible in the same execution.
- Contradiction detection will use the LLM (same model already used for lint) to evaluate whether two claims are factually contradictory — not purely a string-matching approach.
- Contradiction detection is scoped to pages within the same workspace; cross-workspace comparison is out of scope.
- The feature does not auto-resolve contradictions — it only detects and reports them. Resolution remains a human responsibility.
- Pages with fewer than 50 words are excluded from consistency checking to avoid false positives on stub or index pages.
- The scheduled lint task cadence (already configured via the beat scheduler) is sufficient for automatic consistency checks; no new scheduling mechanism is needed.
