# Tasks: Obsidian Read-Only Vault via Git Remote Sync

**Input**: Design documents from `/specs/004-obsidian-git-sync/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/clone-url.md ✅, quickstart.md ✅

**Tests**: Unit tests included in US1 per constitution Principle VI. No TDD explicitly requested — tests written after implementation.

**Organization**: Tasks grouped by user story. Each story is independently implementable and testable.

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other [P] tasks in the same phase
- **[Story]**: User story this task belongs to
- File paths are relative to repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add new config settings and create the `app/git/providers/` package skeleton.

- [ ] T001 Add 5 new `WIKI_GIT_*` settings to `app/config.py`: `wiki_git_enabled` (bool, default `False`), `wiki_git_provider` (str, default `"github"`), `wiki_git_provider_token` (str, default `""`), `wiki_git_org` (str, default `""`), `wiki_git_base_url` (str, default `""` for GitLab self-hosted)
- [ ] T002 Create `app/git/providers/__init__.py` — define abstract `GitProvider` base class with `create_repo(org: str, repo_name: str) -> str` and `get_push_url(remote_url: str) -> str` abstract methods; implement `get_provider(settings) -> GitProvider` factory that returns `GitHubProvider` or `GitLabProvider` based on `settings.wiki_git_provider`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database model changes and migration that all user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 Add three nullable columns to `Workspace` model in `app/models/workspace.py`: `git_remote_url = Column(Text, nullable=True)`, `git_last_push_at = Column(DateTime(timezone=True), nullable=True)`, `git_last_push_error = Column(Text, nullable=True)`
- [ ] T004 Create Alembic migration in `alembic/versions/` — `add_column workspaces.git_remote_url (Text nullable)`, `workspaces.git_last_push_at (DateTime tz nullable)`, `workspaces.git_last_push_error (Text nullable)`; `downgrade()` MUST drop all three columns symmetrically

**Checkpoint**: `make migrate` succeeds; `from app.models.workspace import Workspace` imports cleanly with the three new fields.

---

## Phase 3: User Story 1 — Wiki Changes Reach Obsidian After Ingest (Priority: P1) 🎯 MVP

**Goal**: After every wiki write on the EKS server, the commit is pushed to the configured remote within 60 seconds. Push failures are non-fatal to the operation that triggered them.

**Independent Test**: Configure `WIKI_GIT_ENABLED=true`, run an ingest, check worker logs for `git_push_success` event, verify new commit appears on the remote within 60 seconds.

### Implementation for User Story 1

- [ ] T005 [P] [US1] Add `set_remote(remote_url: str) -> None` and `push_to_remote(token: str) -> str` methods to `RepoManager` in `app/git/repo_manager.py` — `set_remote` calls `repo.create_remote("origin", url)` if no remote exists (idempotent); `push_to_remote` builds `https://{token}@{host}/{path}.git` auth URL in memory, calls `repo.remotes.origin.push()`, returns pushed commit SHA; raises `GitError` on push failure
- [ ] T006 [P] [US1] Create `app/git/providers/github.py` — implement `GitHubProvider(GitProvider)`: `get_push_url(remote_url, token) -> str` builds `https://{token}@github.com/{org}/{repo}.git`; stub `create_repo()` raises `NotImplementedError` (implemented in US3)
- [ ] T007 [P] [US1] Create `app/git/providers/gitlab.py` — implement `GitLabProvider(GitProvider)`: `get_push_url(remote_url, token) -> str` builds auth URL using `WIKI_GIT_BASE_URL` (defaults to `https://gitlab.com`); stub `create_repo()` raises `NotImplementedError`
- [ ] T008 [US1] Create `app/workers/git_push_worker.py` — `push_to_remote` Celery task: sync `def push_to_remote(self, workspace_id: str)`; acquire Redis lock `git_push_lock:{workspace_id}` via `SET NX PX 120000`; if lock unavailable retry with `self.retry(countdown=10, max_retries=6)`; inside `_push_async`: load workspace, call `repo.push_to_remote(token)`, update `workspace.git_last_push_at = now()` and clear `workspace.git_last_push_error` on success, set `workspace.git_last_push_error = str(exc)` on failure; emit `git_push_start`, `git_push_success`, `git_push_error` structured log events; release Redis lock in `finally` block; task name `"app.workers.git_push_worker.push_to_remote"`; skip all work silently when `settings.wiki_git_enabled` is `False` or `workspace.git_remote_url` is `None`
- [ ] T009 [US1] Add `git_push` to the Celery worker queues in `docker-compose.yml` — append `,git_push` to the worker's `CELERY_QUEUES` env var (or `-Q` arg); set `route` for `app.workers.git_push_worker.push_to_remote` → `git_push` in `app/workers/celery_app.py` (or equivalent task routing config)
- [ ] T010 [P] [US1] Wire `push_to_remote.apply_async(args=[str(workspace_id)], queue="git_push")` in `app/workers/ingest_worker.py` — call inside `_process_ingest_job_async` after each successful `repo.write_file()` call that produces a new commit SHA; guard with `if settings.wiki_git_enabled`
- [ ] T011 [P] [US1] Wire `push_to_remote.apply_async(args=[str(workspace_id)], queue="git_push")` in `app/api/v1/wiki.py` — add after successful `repo.write_file()` in `create_page` and `update_page` handlers, and after `repo.delete_file()` in `delete_page` handler; guard with `if settings.wiki_git_enabled`
- [ ] T012 [P] [US1] Wire `push_to_remote.apply_async(args=[str(workspace_id)], queue="git_push")` in `app/mcp/tools/wiki.py` — add after `repo.write_file()` in `create_wiki_page` and `update_wiki_page` tool handlers; guard with `if settings.wiki_git_enabled`
- [ ] T013 [US1] Create `tests/unit/test_git_push_worker.py` — unit tests (no DB, no real Redis): mock `RepoManager.push_to_remote`, mock Redis `SET NX`, mock `AsyncSessionLocal`; test: push succeeds → `git_last_push_at` set and `git_last_push_error` cleared; push fails → `git_last_push_error` set, task does NOT raise; lock unavailable → task retries; `WIKI_GIT_ENABLED=False` → push skipped with no error; `git_remote_url` is None → push skipped

**Checkpoint**: `WIKI_GIT_ENABLED=true` + ingest job → `git_push_success` in worker logs → remote has new commit.

---

## Phase 4: User Story 2 — Developer Gets Clone URL in Under 5 Minutes (Priority: P2)

**Goal**: Workspace members can call one endpoint to get the HTTPS clone URL and Obsidian setup instructions.

**Independent Test**: Call `GET /api/v1/workspaces/{id}/clone-url` with a valid member token → 200 with `clone_url`; call with non-member token → 403; call for workspace with null `git_remote_url` → 409.

### Implementation for User Story 2

- [ ] T014 [US2] Add `WorkspaceCloneUrlResponse` Pydantic response model and `GET /{workspace_id}/clone-url` endpoint to `app/api/v1/workspaces.py` — require `reader` role minimum via `require_role`; return 409 with descriptive `detail` if `workspace.git_remote_url` is `None`; response body matches contract in `specs/004-obsidian-git-sync/contracts/clone-url.md`: `clone_url`, `workspace_slug`, `last_push_at`, `setup` (with `clone_command`, `obsidian_note`, `plugin_url`)

**Checkpoint**: `GET /clone-url` returns 200 for members, 403 for non-members, 409 when no remote configured.

---

## Phase 5: User Story 3 — New Workspace Auto-Provisions Remote Repository (Priority: P3)

**Goal**: Creating a workspace when `WIKI_GIT_ENABLED=true` automatically creates and links a remote git repo. Failures are non-fatal.

**Independent Test**: Create workspace with `WIKI_GIT_ENABLED=true` → remote repo exists in provider → workspace `git_remote_url` is set → first ingest pushes successfully.

### Implementation for User Story 3

- [ ] T015 [P] [US3] Implement `GitHubProvider.create_repo(org: str, repo_name: str) -> str` in `app/git/providers/github.py` — call `POST /orgs/{org}/repos` via `urllib.request` with `Authorization: Bearer {token}` header; body `{"name": repo_name, "private": true, "auto_init": false}`; return `clone_url` from response; idempotent: if response is 422 (already exists), call `GET /repos/{org}/{repo_name}` and return its `clone_url`; `repo_name` convention: `wiki-{workspace.slug}`
- [ ] T016 [P] [US3] Implement `GitLabProvider.create_repo(org: str, repo_name: str) -> str` in `app/git/providers/gitlab.py` — call `POST {base_url}/api/v4/projects` with `PRIVATE-TOKEN: {token}` header; body `{"name": repo_name, "namespace_id": {group_id}, "visibility": "private"}`; idempotent on 409; return `http_url_to_repo`; `WIKI_GIT_BASE_URL` defaults to `https://gitlab.com`
- [ ] T017 [US3] Wire auto-provision in workspace create handler in `app/api/v1/workspaces.py` — after `repo.init()`, if `settings.wiki_git_enabled`: call `get_provider(settings).create_repo(settings.wiki_git_org, f"wiki-{ws.slug}")` in a `try/except`; on success call `repo.set_remote(clone_url)` and set `ws.git_remote_url = clone_url`; on failure log `git_remote_provision_error` warning and continue (workspace creation is NOT rolled back)

**Checkpoint**: `POST /workspaces` with `WIKI_GIT_ENABLED=true` → remote repo appears in GitHub/GitLab → `GET /clone-url` returns the URL.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Lint, type safety, docs.

- [ ] T018 [P] Run `make lint` (ruff + mypy) across `app/git/providers/`, `app/workers/git_push_worker.py`, and all modified files; fix any type errors or style violations; ensure all public functions have type annotations
- [ ] T019 [P] Update `README.md` — add a "Git Remote Sync (Obsidian)" subsection under the Operations chapter documenting the 5 env vars, the `GET /clone-url` endpoint, and the Obsidian Git plugin setup steps (mirror `specs/004-obsidian-git-sync/quickstart.md`)
- [ ] T020 Update `CLAUDE.md` Recent Changes section to document the git remote sync feature and new `app/git/providers/` package

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **blocks all user stories**
- **US1 (Phase 3)**: Depends on Phase 2 — no dependency on US2 or US3
- **US2 (Phase 4)**: Depends on Phase 2 — independent of US1 (reads `git_remote_url` column; doesn't need push to work)
- **US3 (Phase 5)**: Depends on Phase 2 — independent of US1 and US2 (creates remote; US1 uses it to push)
- **Polish (Phase 6)**: Depends on all user story phases

### User Story Dependencies

- **US1 (P1)**: Only needs the 3 new columns (Phase 2) + config settings (Phase 1)
- **US2 (P2)**: Only needs `git_remote_url` column (Phase 2) — fully independent from US1
- **US3 (P3)**: Only needs `git_remote_url` column (Phase 2) + providers package (Phase 1) — populates the URL that US2 reads

> US2 and US3 can run in parallel after Phase 2 completes. US1 can also run in parallel with both.

### Parallel Opportunities

- T005, T006, T007 in Phase 3 touch different files — run in parallel
- T010, T011, T012 in Phase 3 touch different files — run in parallel after T008 and T009
- T015, T016 in Phase 5 touch different files — run in parallel
- T018, T019 in Phase 6 are independent — run in parallel
- US2 (Phase 4) and US3 (Phase 5) can run in parallel with US1 (Phase 3) after Phase 2 completes

---

## Parallel Example: User Story 1 (Phase 3)

```bash
# Step 1 — all three can run in parallel (different files):
Task T005: "Add set_remote() + push_to_remote() to app/git/repo_manager.py"
Task T006: "Create app/git/providers/github.py"
Task T007: "Create app/git/providers/gitlab.py"

# Step 2 — sequential (T008 depends on T005-T007):
Task T008: "Create app/workers/git_push_worker.py"
Task T009: "Add git_push queue to docker-compose.yml"

# Step 3 — all three can run in parallel (different files):
Task T010: "Wire push trigger in app/workers/ingest_worker.py"
Task T011: "Wire push trigger in app/api/v1/wiki.py"
Task T012: "Wire push trigger in app/mcp/tools/wiki.py"

# Step 4 — sequential after T010-T012:
Task T013: "Create tests/unit/test_git_push_worker.py"
```

## Parallel Example: US2 + US3 alongside US1

```bash
# After Phase 2 completes, start all three simultaneously:
Developer A → Phase 3 (T005–T013): Push sync
Developer B → Phase 4 (T014):      Clone-URL endpoint
Developer C → Phase 5 (T015–T017): Auto-provision
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T002)
2. Complete Phase 2: Foundational (T003–T004) — **do not skip**
3. Complete Phase 3: User Story 1 (T005–T013)
4. **STOP and VALIDATE**: Set `WIKI_GIT_ENABLED=true`, run ingest, confirm push in logs, confirm commit on remote
5. Ship US1 — developers can now manually clone the remote and open in Obsidian

### Incremental Delivery

1. Setup + Foundational → skeleton ready
2. US1 (push sync) → validate → **MVP: wiki pages reach Obsidian**
3. US2 (clone-URL endpoint) → validate → self-service vault setup
4. US3 (auto-provision) → validate → zero-touch workspace onboarding
5. Polish → lint + docs → merge

---

## Notes

- `[P]` tasks = different files, no shared write dependencies — safe to run simultaneously
- `[US1/2/3]` label maps each task to its user story for traceability
- T006 and T007 create provider files with stub `create_repo()` — T015 and T016 complete them in US3
- The Redis lock in T008 uses the existing `get_redis_pool()` — no new Redis connection needed
- All push triggers (T010, T011, T012) must guard with `if settings.wiki_git_enabled` to keep the feature fully opt-in
- No database migrations are needed beyond T004 — the three columns cover all three user stories
