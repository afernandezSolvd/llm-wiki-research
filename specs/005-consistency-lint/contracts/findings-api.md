# Contract: Findings API — Consistency Finding Shape

**Branch**: `005-consistency-lint` | **Date**: 2026-04-27

## No API Changes Required

Consistency findings are returned by the **existing** findings endpoint:

```
GET /api/v1/workspaces/{workspace_id}/lint/{run_id}/findings
```

No new endpoints. The existing `LintFindingSummary` response schema already includes `finding_type` as a free string, so `"consistency"` findings will surface automatically.

---

## Consistency Finding Response Shape

A consistency finding returned by the existing findings API will look like:

```json
{
  "id": "uuid",
  "finding_type": "consistency",
  "severity": "error",
  "page_title": "Redis",
  "description": "Conflicting claims about Redis port: page A says 6379, page B says 6380.",
  "evidence": {
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
}
```

## Quality Dashboard Contract

The existing `GET /api/v1/workspaces/{workspace_id}/status/quality` endpoint returns a `lint_summary` block. Consistency findings will appear in `lint_summary.findings` with `finding_type: "consistency"` — no changes to the response schema required.

## Lint Trigger Contract (unchanged)

```
POST /api/v1/workspaces/{workspace_id}/lint
```

No request body changes. The existing trigger creates a full-scope LintRun. The new auto-trigger (from ingest) creates an incremental-scope LintRun internally — not exposed as a new API surface.
