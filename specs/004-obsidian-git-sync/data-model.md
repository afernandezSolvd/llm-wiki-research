# Data Model: Obsidian Git Remote Sync

## Modified Entity: Workspace

Three new nullable columns added to the existing `workspaces` table. No new table required.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `git_remote_url` | Text | Yes | HTTPS clone URL (without embedded token). e.g. `https://github.com/acme/ws-my-project.git`. Null = remote not configured. |
| `git_last_push_at` | DateTime (tz-aware) | Yes | Timestamp of the most recent successful push. Null = never pushed. |
| `git_last_push_error` | Text | Yes | Error message from the most recent failed push. Cleared on success. Null = no error. |

**State transitions for `git_remote_url`**:
```
null → configured    (on workspace create when WIKI_GIT_ENABLED=true, or on manual admin call)
configured → null    (if remote is deconfigured — out of scope for v1, admin DB operation only)
```

**Index**: No index needed — remote URL is never queried in bulk.

---

## New Entity: PushTask (Celery task, no DB model)

Push tasks are ephemeral Celery jobs. They are NOT persisted in the database — task status lives in the Celery result backend (Redis). The `git_last_push_at` and `git_last_push_error` on the Workspace row serve as the durable audit trail.

**Task payload**:
```python
{
  "workspace_id": str(UUID)   # passed as positional arg to Celery task
}
```

**Redis lock key**: `git_push_lock:{workspace_id}` — TTL 120 seconds, acquired with SET NX PX.

---

## New Entity: GitProvider (in-process, no DB model)

An abstract interface resolved at runtime from `WIKI_GIT_PROVIDER` env var.

**Interface**:
```
create_repo(org: str, repo_name: str, private: bool = True) → remote_url: str
  Idempotent — if repo already exists, returns its URL without error.
```

**Implementations**: `GitHubProvider`, `GitLabProvider`

**Repo naming convention**: `{WIKI_GIT_ORG}/wiki-{workspace.slug}` (e.g. `acme/wiki-engineering-team`)

---

## New Config Settings (app/config.py)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `wiki_git_enabled` | bool | `False` | Master toggle — disables all push scheduling when False |
| `wiki_git_provider` | str | `"github"` | `"github"` or `"gitlab"` |
| `wiki_git_provider_token` | str | `""` | PAT/token for API calls and push auth |
| `wiki_git_org` | str | `""` | GitHub org or GitLab namespace for repo creation |
| `wiki_git_base_url` | str | `""` | GitLab instance URL (e.g. `https://gitlab.company.com`); empty = gitlab.com |

---

## Migration

One Alembic migration adds the three columns to `workspaces`:

```python
# upgrade
op.add_column("workspaces", sa.Column("git_remote_url", sa.Text(), nullable=True))
op.add_column("workspaces", sa.Column("git_last_push_at", sa.DateTime(timezone=True), nullable=True))
op.add_column("workspaces", sa.Column("git_last_push_error", sa.Text(), nullable=True))

# downgrade
op.drop_column("workspaces", "git_remote_url")
op.drop_column("workspaces", "git_last_push_at")
op.drop_column("workspaces", "git_last_push_error")
```
