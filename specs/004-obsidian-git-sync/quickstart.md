# Quickstart: Obsidian Git Remote Sync

## Prerequisites

- Docker stack running on EKS (`make up` or kubectl deployment)
- A GitHub org (or GitLab group) where the server can create private repos
- A GitHub fine-grained PAT (or GitLab PAT) with `repo` scope

## 1 — Configure the server

Add to your `.env` (or Kubernetes Secret → env vars):

```bash
WIKI_GIT_ENABLED=true
WIKI_GIT_PROVIDER=github          # or "gitlab"
WIKI_GIT_PROVIDER_TOKEN=ghp_...   # fine-grained PAT, repo scope
WIKI_GIT_ORG=acme-corp            # GitHub org or GitLab namespace
# WIKI_GIT_BASE_URL=              # only needed for self-hosted GitLab
```

Restart the API and worker pods to pick up new env vars.

## 2 — Verify remote is provisioned for a workspace

When a new workspace is created with `WIKI_GIT_ENABLED=true`, a remote repo is auto-created. For existing workspaces, check:

```bash
# List workspaces and look for git_remote_url field
curl -s http://your-eks-host/api/v1/workspaces \
  -H "Authorization: Bearer $TOKEN" | jq '.[].git_remote_url'
```

If `null`, the workspace predates this feature. A backfill migration or admin script will be needed (out of scope for v1 — remote can be configured manually via DB for now).

## 3 — Trigger an ingest and verify push

```bash
# Ingest a URL
curl -X POST http://your-eks-host/api/v1/workspaces/$WS_ID/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/your-doc"}'

# Watch worker logs for push confirmation
kubectl logs -f deployment/context-worker | grep git_push
# Expected: {"event": "git_push_success", "workspace_id": "...", "sha": "..."}
```

## 4 — Clone and open in Obsidian

```bash
# Get clone URL for your workspace
curl http://your-eks-host/api/v1/workspaces/$WS_ID/clone-url \
  -H "Authorization: Bearer $TOKEN"
# → {"clone_url": "https://github.com/acme-corp/wiki-my-team.git", ...}

# Clone it
git clone https://github.com/acme-corp/wiki-my-team.git ~/wiki-my-team

# Open in Obsidian: File → Open Vault → ~/wiki-my-team
```

## 5 — Set up auto-pull in Obsidian

1. Open Obsidian Settings → Community Plugins → Browse → search "Obsidian Git"
2. Install and enable the plugin
3. Settings → Obsidian Git → set "Pull interval" to `1` (minutes)
4. Optionally enable "Pull on startup"

From this point, every ingest on the server automatically appears in Obsidian within ~90 seconds.

## Verify end-to-end

```bash
# Ingest something new
curl -X POST http://your-eks-host/api/v1/workspaces/$WS_ID/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"url": "https://your-doc-url.com"}'

# Wait ~60s, then in the vault directory:
git pull
# → new/updated .md files appear

# Open Obsidian — new pages visible in graph view
```

## Push failure scenario

```bash
# Simulate provider outage (revoke token temporarily)
# Run an ingest — it still completes:
# {"event": "ingest_complete", "workspace_id": "..."}
# {"event": "git_push_error", "workspace_id": "...", "error": "...401...", "attempt": 1}
# Task retries up to 6 times with 10s backoff, then gives up.
# wiki_pages table and git history are intact; only remote is behind.
```
