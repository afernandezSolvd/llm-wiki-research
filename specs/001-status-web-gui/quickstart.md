# Quickstart: Status Web GUI

**Branch**: `001-status-web-gui` | **Date**: 2026-04-21

## Prerequisites

- Full stack running: `make up`
- No credentials required — the dashboard is public and self-authenticating

## Step 1: Open the Dashboard

Navigate to:
```
http://localhost:8000/status
```

The dashboard silently fetches a server-issued read-only JWT from
`GET /api/v1/status/bootstrap` and auto-selects the first available workspace.
No login form or token input is needed.

## Step 2: View Your Workspace

If more than one workspace exists, a dropdown at the top lets you switch
between them. The dashboard loads the three panels:

- **Health**: Component status (workers, database, broker)
- **Jobs**: Active, queued, and recent failed jobs
- **Quality**: Drift alerts and latest lint findings

Each panel auto-refreshes every 20 seconds. The last-updated timestamp is
shown at the bottom of each panel.

## Step 3: Inspect a Failed Job

In the **Jobs** panel, failed jobs are highlighted. Click on a job row to
expand the error message and retry count.

## Step 4: Review Drift Alerts

In the **Quality** panel, wiki pages are listed by drift severity. Error-
severity pages (drift > 0.70) are shown first. Click a page title to open
its wiki page in the main application.

## Step 5: Platform Admin View (Admins Only)

If your user has the `platform_admin` flag, an additional **"All Workspaces"**
tab is visible at the top. This shows a summary table of active jobs, recent
failures, drift counts, and lint finding counts across every workspace.

---

## Validating the Feature Works

```bash
# 1. Bootstrap — get server-issued token and workspace list (no credentials needed)
BOOTSTRAP=$(curl -s http://localhost:8000/api/v1/status/bootstrap)
TOKEN=$(echo "$BOOTSTRAP" | jq -r .access_token)
WS_ID=$(echo "$BOOTSTRAP" | jq -r '.workspaces[0].id')

# 2. Check component health
curl -s "http://localhost:8000/api/v1/workspaces/$WS_ID/status/components" \
  -H "Authorization: Bearer $TOKEN" | jq .

# 3. Check recent jobs
curl -s "http://localhost:8000/api/v1/workspaces/$WS_ID/status/jobs" \
  -H "Authorization: Bearer $TOKEN" | jq .

# 4. Check quality metrics
curl -s "http://localhost:8000/api/v1/workspaces/$WS_ID/status/quality" \
  -H "Authorization: Bearer $TOKEN" | jq .

# 5. Check admin aggregate (platform_admin only)
curl -s http://localhost:8000/api/v1/admin/status \
  -H "Authorization: Bearer $TOKEN" | jq .

# 6. Open dashboard in browser (zero-click — loads data automatically)
open http://localhost:8000/status
```

## Troubleshooting

**Dashboard shows all workers as "unreachable"**
- Verify workers are running: `docker compose ps`
- Check Redis is reachable: `redis-cli ping`
- Celery inspect uses a 2-second timeout; if workers are under heavy load they
  may not respond in time

**No drift alerts appear**
- Drift alerts only appear after a wiki page has been updated at least once
  since creation (so `embedding` differs from `original_embedding`)
- Verify `DRIFT_ALERT_THRESHOLD` in your `.env` (default `0.35`)

**Jobs panel is empty**
- Only jobs from the last 24 hours are shown
- Trigger a test ingest: `POST /api/v1/workspaces/{ws_id}/ingest`
