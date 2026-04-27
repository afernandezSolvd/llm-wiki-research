# Data Model: Consistency Lint

**Branch**: `005-consistency-lint` | **Date**: 2026-04-27

## No New Tables or Columns

This feature requires **no schema migrations**. All necessary storage already exists.

---

## Existing Entities Used (Unchanged Schema)

### LintFinding (existing — `lint_findings` table)

| Column | Type | Role in this feature |
|---|---|---|
| `finding_type` | String(30) | New value: `"consistency"` (was `"contradiction"`) |
| `wiki_page_id` | UUID FK (nullable) | Points to the primary page in the contradiction |
| `severity` | String(10) | `"error"` for all consistency findings |
| `description` | Text | Human-readable summary of the contradiction |
| `evidence` | JSONB | Extended schema (see below) |

### LintFinding.evidence JSONB — Extended Schema

For consistency findings, the `evidence` object will follow this structure:

```json
{
  "conflicting_pages": [
    {
      "path": "pages/entities/redis.md",
      "excerpt": "Redis runs on port 6379"
    },
    {
      "path": "pages/summaries/docker-compose-yml.md",
      "excerpt": "Redis is configured on port 6380"
    }
  ],
  "topic": "Redis port configuration",
  "pair_source": "kg_community"
}
```

Fields:
- `conflicting_pages` — list of `{path, excerpt}` for every page involved (2 or more)
- `topic` — the entity or claim at the center of the contradiction (LLM-extracted)
- `pair_source` — how the candidate pair was found: `"kg_community"` or `"embedding_similarity"`

Backward compatibility: `page_a`, `page_b`, `page_a_excerpt`, `page_b_excerpt` keys are preserved for two-page findings for API consumers that already parse the old structure.

---

### LintRun (existing — `lint_runs` table)

No column changes. The `scope` field already supports `"incremental"` and `page_ids_scoped` already supports scoped page lists for post-ingest lint passes.

---

### WikiPage (existing — `wiki_pages` table)

No changes. The `embedding` column (Vector(1024)) is used by the new embedding-similarity candidate pairing.

---

## Data Flow

```
Ingest completes
    │
    ▼
LintRun created (scope="incremental", page_ids_scoped=[touched_page_ids])
    │
    ▼
run_lint_pass Celery task
    │
    ├── Phase 1: Orphan check (existing)
    ├── Phase 2: Semantic drift (existing)
    └── Phase 3: Consistency check (enhanced)
            │
            ├── KG community pairs (existing, type renamed "consistency")
            └── Embedding-similarity pairs (new, for non-KG pages)
                    │
                    ▼
            LintFinding(finding_type="consistency", evidence={conflicting_pages, topic, pair_source})
```
