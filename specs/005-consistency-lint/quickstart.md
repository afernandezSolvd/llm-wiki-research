# Quickstart: Testing Consistency Lint

**Branch**: `005-consistency-lint` | **Date**: 2026-04-27

## Scenario 1: Manually trigger consistency check and see findings

```bash
# 1. Trigger a lint run
curl -X POST http://localhost:8001/api/v1/workspaces/$WS_ID/lint \
  -H "Authorization: Bearer $TOKEN"
# → { "id": "<run_id>", "status": "queued" }

# 2. Wait for completion
curl http://localhost:8001/api/v1/workspaces/$WS_ID/lint/$RUN_ID \
  -H "Authorization: Bearer $TOKEN"
# → { "status": "done", "finding_count": N }

# 3. Fetch findings — look for finding_type = "consistency"
curl http://localhost:8001/api/v1/workspaces/$WS_ID/lint/$RUN_ID/findings \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | select(.finding_type == "consistency")'
```

**Expected**: Any pages with contradictory factual claims appear as `finding_type: "consistency"`, `severity: "error"`, with `evidence.conflicting_pages` listing both pages and their excerpts.

---

## Scenario 2: Verify auto-trigger after ingest

```bash
# 1. Upload a source that contradicts an existing page
curl -X POST http://localhost:8001/api/v1/workspaces/$WS_ID/sources \
  -H "Authorization: Bearer $TOKEN" \
  -F "title=test-contradiction" \
  -F "file=@test_source_with_contradiction.txt"

# 2. Trigger ingest
curl -X POST http://localhost:8001/api/v1/workspaces/$WS_ID/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"source_ids\": [\"<source_id>\"]}"

# 3. Wait for ingest to complete, then check for a new lint run
curl http://localhost:8001/api/v1/workspaces/$WS_ID/status/jobs \
  -H "Authorization: Bearer $TOKEN" | jq '.jobs[] | select(.queue == "lint")'
```

**Expected**: A lint run with `scope: "incremental"` appears automatically after ingest completes, without any manual lint trigger.

---

## Scenario 3: Verify no false positives on paraphrased facts

```bash
# Upload two sources that say the same thing in different words
# e.g., "Redis uses port 6379" and "The Redis service listens on 6379"
# Run lint — verify zero consistency findings are produced
```

**Expected**: `finding_count` for consistency type = 0.

---

## Scenario 4: Quality dashboard shows consistency findings

```bash
curl http://localhost:8001/api/v1/workspaces/$WS_ID/status/quality \
  -H "Authorization: Bearer $TOKEN" | jq '.lint_summary.findings[] | select(.finding_type == "consistency")'
```

**Expected**: Consistency findings appear in the quality dashboard `lint_summary` block alongside drift and orphan findings.
