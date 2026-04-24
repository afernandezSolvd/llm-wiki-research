# Research: Obsidian Git Remote Sync

## Decision 1 — Git push authentication strategy

**Decision**: HTTPS with token embedded in the remote URL at push time, held only in memory.

**Rationale**: gitpython's `.push()` picks up credentials from the remote URL directly. The token is read from an env var (`WIKI_GIT_PROVIDER_TOKEN`) at push time and embedded as `https://{token}@github.com/{org}/{repo}.git` in memory — it is never written to `.git/config` or disk. This is the standard pattern for server-side CI/CD automation and is well-supported by gitpython. The alternative (Git credential helper) requires filesystem configuration on the EKS node, which is complex to manage in containers.

**Alternatives considered**:
- Git credential helper: Requires writing a shell script to disk in the container; fragile in ephemeral pods.
- SSH deploy keys: Per-repo key management becomes unmanageable at scale (one key per workspace × N workspaces).
- GitHub App: More secure long-term, but adds OAuth complexity and a new dependency. Suitable for a future hardening sprint.

---

## Decision 2 — Git provider API for remote repo creation

**Decision**: Abstract behind a thin `GitProvider` interface with two implementations: `GitHubProvider` and `GitLabProvider`. Provider is selected by `WIKI_GIT_PROVIDER` env var (`github` | `gitlab`). Both are called via standard `urllib.request` or `httpx` (already in the project's transitive deps) — no new SDK dependency.

**GitHub**: `POST /orgs/{org}/repos` with a fine-grained PAT scoped to `repo` (contents: read+write, metadata: read). Org must allow fine-grained tokens.

**GitLab**: `POST /projects` with a personal or group access token scoped to `api` + `write_repository`. Namespace is controlled by `WIKI_GIT_ORG`.

**Rationale**: A thin interface keeps the provider swap to one env-var change. Adding a full SDK (PyGithub, python-gitlab) for two API calls would be over-engineering.

**Alternatives considered**:
- AWS CodeCommit: No standard git push auth pattern, poor tooling outside AWS, not used by most teams.
- Single GitHub-only implementation: Too restrictive for GitLab-first teams.

---

## Decision 3 — Push task serialization per workspace

**Decision**: Redis distributed lock with key `git_push_lock:{workspace_id}`, TTL 120 seconds. The `push_to_remote` Celery task acquires the lock at start. If the lock is already held, the task retries after 10 seconds (max 6 retries = 60s window). Uses `redis-py`'s `SET NX PX` command — no new dependency (Redis is already in the project).

**Rationale**: This prevents concurrent pushes to the same repo, which would cause git push conflicts. celery-singleton / celery-once are third-party libraries and add a dependency; a direct Redis lock is 10 lines of code with no new dep. The 120s TTL ensures the lock is always released even if the worker pod crashes.

**Alternatives considered**:
- Single-concurrency Celery queue per workspace: Requires dynamically creating queues, which is operationally complex.
- celery-singleton library: Adds a dependency for functionality achievable with existing Redis.
- Optimistic retry without locking: Would allow concurrent pushes if two tasks start within milliseconds of each other.

---

## Decision 4 — Where push tasks are triggered

**Decision**: Push tasks are scheduled explicitly by the **callers** of `RepoManager.write_file()` and `delete_file()` — specifically in `ingest_worker.py` (after wiki page commit) and `app/api/v1/wiki.py` (after manual edit/delete). The MCP tool handlers in `app/mcp/tools/wiki.py` also schedule after writing.

**Rationale**: Triggering from inside `RepoManager` would require importing the Celery app, creating a circular import (constitution Principle III forbids module-level `app.*` imports in worker-adjacent code). Explicit scheduling at the call site is more transparent and easier to test.

**Alternatives considered**:
- Trigger inside `RepoManager`: Circular import risk; mixes git storage with task orchestration.
- Post-commit git hook: Not possible in gitpython's local repos without extra setup.

---

## Decision 5 — Workspace model changes

**Decision**: Add three nullable columns to the `workspaces` table: `git_remote_url` (Text), `git_last_push_at` (DateTime with timezone), `git_last_push_error` (Text). No new table.

**Rationale**: A separate `workspace_remotes` table would be over-normalized — one workspace has at most one remote. Storing on the workspace row avoids a join and keeps the migration minimal.

**Alternatives considered**:
- Separate `workspace_remotes` table: Justified only if multiple remotes per workspace were needed (not in scope).
- Store in workspace `settings` JSONB: Loses type safety, makes migrations harder, harder to query.

---

## Decision 6 — New Celery queue

**Decision**: Add a `git_push` queue. The push worker runs with concurrency=2 (low — push tasks are I/O-bound but not high-frequency). Added to `docker-compose.yml` worker `CELERY_QUEUES` env and to the Kubernetes worker Deployment.

**Rationale**: Isolating push tasks prevents a queue backup (e.g., large batch ingest) from delaying pushes. The ingest, lint, embedding, and graph queues remain unchanged.
