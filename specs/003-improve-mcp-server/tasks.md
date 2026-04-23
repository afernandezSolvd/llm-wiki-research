# Tasks: Improve MCP Server with Anthropic Best Practices

**Input**: Design documents from `/specs/003-improve-mcp-server/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/mcp-tools.md ✅, quickstart.md ✅

**Tests**: Not explicitly requested — unit tests included in Polish phase per constitution Principle VI.

**Organization**: Tasks grouped by user story. Each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other [P] tasks in the same phase
- **[Story]**: User story this task belongs to
- File paths are relative to repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the `mcp` SDK dependency and create the `app/mcp/` package skeleton.

- [x] T001 Add `mcp>=1.25,<2` to the `[project].dependencies` list in `pyproject.toml`
- [x] T002 Create `app/mcp/__init__.py` as an empty package init
- [x] T003 Create `app/mcp/tools/__init__.py` as an empty package init

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the shared infrastructure that all three user stories depend on — the `MCPResponse` envelope and the `FastMCP` server instance. No tools are registered here; tools are added per story.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 Create `app/mcp/response.py` — define `MCPResponse` dataclass with `summary: str`, `data: dict`, and `error: dict | None` fields; add `to_json() -> str` method that serializes to the envelope format defined in `specs/003-improve-mcp-server/data-model.md`
- [x] T005 Create `app/mcp/server.py` — instantiate `FastMCP("context-wiki")` and add a `run_stdio()` entry point that calls `mcp.run(transport="stdio")`; add `if __name__ == "__main__": run_stdio()` guard so the module is runnable as `python -m app.mcp.server`
- [x] T006 Add a `get_auth_context()` helper to `app/mcp/server.py` that reads the `Authorization: Bearer <token>` header from FastMCP's request context and returns the decoded user; raises `MCPError` (HTTP 401) if the token is missing or invalid — this helper is shared by all workspace-scoped tool handlers

**Checkpoint**: `python -m app.mcp.server` starts without error; `from app.mcp.response import MCPResponse` imports cleanly.

---

## Phase 3: User Story 1 — Intent-Focused Tool Surface (Priority: P1) 🎯 MVP

**Goal**: Replace the `@ivotoby/openapi-mcp-server` npm bridge with 13 purpose-built tools. Existing Claude Code and Kiro stdio users reconnect automatically with the new, smaller tool surface.

**Independent Test**: Start Claude Code, connect to the MCP, and ask it to "list my workspaces then query what the wiki knows about authentication." Passes if the agent uses ≤ 2 tool calls (no chaining of raw CRUD endpoints) and returns a formatted answer with citations.

### Implementation for User Story 1

- [x] T007 [P] [US1] Create `app/mcp/tools/workspaces.py` — implement `list_workspaces()` (calls `GET /api/v1/workspaces`) and `get_workspace_status(workspace_id)` (aggregates `/status/quality`, `/status/jobs`, `/status/components` into one `WorkspaceStatus` payload); each function returns `MCPResponse.to_json()`; use tool descriptions from `specs/003-improve-mcp-server/contracts/mcp-tools.md`
- [x] T008 [P] [US1] Create `app/mcp/tools/ingest.py` — implement `ingest_url(workspace_id, url, title?)`, `ingest_file(workspace_id, filename, content_base64, title?)`, and `get_ingest_status(workspace_id, job_id)`; `ingest_url` must call source-create then trigger-ingest in sequence before returning `IngestResult`; responses follow `specs/003-improve-mcp-server/data-model.md`
- [x] T009 [P] [US1] Create `app/mcp/tools/query.py` — implement `query_wiki(workspace_id, question, top_k?, user_context?)`; reuse the existing async query pipeline from `app/api/v1/query.py` (call `_build_retrieval_context` and the LLM step directly rather than via HTTP); return `QueryResult` in `MCPResponse` envelope
- [x] T010 [P] [US1] Create `app/mcp/tools/wiki.py` — implement `list_wiki_pages(workspace_id, prefix?)`, `get_wiki_page(workspace_id, page_path)`, `create_wiki_page(workspace_id, page_path, content)`, and `update_wiki_page(workspace_id, page_path, content)`; map to existing `app/api/v1/wiki.py` handler logic; normalize `page_path` (strip leading `/` if present)
- [x] T011 [P] [US1] Create `app/mcp/tools/sources.py` — implement `list_sources(workspace_id)`; map to existing `app/api/v1/sources.py` list handler; return `SourceItem[]` in `MCPResponse` envelope
- [x] T012 [P] [US1] Create `app/mcp/tools/quality.py` — implement `trigger_lint(workspace_id)`; call the lint trigger logic from `app/api/v1/lint.py`; return `LintRunResult` in `MCPResponse` envelope
- [x] T013 [US1] Register all 12 tools (from T007–T012) in `app/mcp/server.py` using `@mcp.tool()` decorators; import each tool module inside the registration function (not at module level) to follow the lazy-import pattern from constitution Principle III; confirm total tool count is ≤ 15
- [x] T014 [US1] Update `.claude/mcp-context-wiki.sh` — replace the `npx @ivotoby/openapi-mcp-server` invocation with `exec python -m app.mcp.server`; keep the auth proxy health-check loop at the top of the script unchanged
- [x] T015 [US1] Update `.mcp.json` — change the `context-wiki` server `command` to `python` and `args` to `["-m", "app.mcp.server"]`; remove the `@ivotoby/openapi-mcp-server` npx invocation; preserve the `description` field

**Checkpoint**: Claude Code MCP reconnects after `.mcp.json` change; `tools/list` returns ≤ 15 tools; agent can complete a list-workspaces + query-wiki task in ≤ 2 tool calls.

---

## Phase 4: User Story 2 — Deferred Tool Loading (Priority: P2)

**Goal**: Reduce tool-definition token usage by ≥ 50% compared to the old npm bridge. Primary lever is the tool count reduction from Phase 3. Additional work: optimize descriptions to be concise, and implement the `search_tools` meta-tool for on-demand schema access.

**Independent Test**: Count the tokens in the `tools/list` response from the new server vs. the old npm bridge. Passes if the new manifest is ≤ 50% of the old token count. Also passes if a query-only agent session never loads ingest tool schemas.

### Implementation for User Story 2

- [x] T016 [P] [US2] Audit all 12 tool descriptions across `app/mcp/tools/*.py` — each `description=` argument to `@mcp.tool()` must be ≤ 60 words and start with a verb phrase (e.g., "Returns all workspaces…", "Ingests a web URL…"); rewrite any that exceed the limit or are passive/vague
- [x] T017 [P] [US2] Create `app/mcp/tools/meta.py` — implement `search_tools(query: str)` that accepts a keyword string, matches it against tool names and descriptions in the server's tool registry, and returns the full `inputSchema` for matching tools as `ToolSchemaResult[]` in `MCPResponse` envelope; this is the on-demand schema fetch mechanism described in `specs/003-improve-mcp-server/research.md` Decision 3
- [x] T018 [US2] Register `search_tools` in `app/mcp/server.py` using `@mcp.tool()` — brings total to 13 tools; confirm count is still ≤ 15

**Checkpoint**: `tools/list` token count is ≤ 50% of old bridge output. `search_tools("ingest")` returns full schemas for `ingest_url`, `ingest_file`, and `get_ingest_status`.

---

## Phase 5: User Story 3 — HTTP/Remote Transport Support (Priority: P3)

**Goal**: Add Streamable HTTP transport at `POST /mcp` on the main FastAPI app, enabling cloud-hosted agents to connect without a local subprocess.

**Independent Test**: From a machine without a local Python process running, point a Claude agent at the `POST /mcp` endpoint with a valid bearer token. Passes if `tools/list` returns all 13 tools and `query_wiki` completes successfully.

### Implementation for User Story 3

- [x] T019 [US3] Mount the MCP Streamable HTTP transport in `app/main.py` — import `mcp_app` from `app/mcp/server.py` (the FastAPI sub-application generated by `FastMCP.streamable_http_app()`) and mount it at `/mcp`; set `stateless_http=True` for horizontal scalability
- [x] T020 [US3] Verify bearer token auth is enforced on `POST /mcp` in `app/main.py` — add the `get_current_user` dependency to the `/mcp` mount or its router so unauthenticated requests receive HTTP 401 before reaching any MCP handler; write a brief manual test in `specs/003-improve-mcp-server/quickstart.md` showing the `curl -X POST /mcp` command with and without auth header

**Checkpoint**: `curl -X POST http://localhost:8000/mcp -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'` without auth returns 401; with `Authorization: Bearer <token>` returns the 13-tool manifest.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Unit tests (constitution Principle VI), structured logging (Principle V), and cleanup.

- [x] T021 [P] Create `tests/unit/test_mcp_tools.py` — add unit tests for the `MCPResponse` envelope (T004), `ingest_url` input validation (workspace_id UUID check, URL scheme check), `query.py` query_wiki parameter defaults, and `wiki.py` page_path normalization (leading-slash strip); mock all DB and service calls at the function boundary per constitution Principle VI
- [x] T022 [P] Add `logger.info("mcp_tool_call", tool=<name>, workspace_id=<id>)` structured logging at the start of every tool handler in `app/mcp/tools/*.py` and `logger.info("mcp_tool_error", tool=<name>, error=<str>)` on exceptions — follows constitution Principle V (no f-string log messages)
- [x] T023 Run `make lint` (ruff + mypy) and fix any type errors or style violations introduced in `app/mcp/`; ensure `app/mcp/server.py` has proper type annotations on all public functions
- [x] T024 [P] Remove the Node.js `@ivotoby/openapi-mcp-server` dependency from `package.json` if present in the project root; update any Docker or CI references that installed it

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — **blocks all user stories**
- **User Story 1 (Phase 3)**: Depends on Phase 2 — no dependencies on US2 or US3
- **User Story 2 (Phase 4)**: Depends on Phase 3 (needs the 12 tools registered before auditing descriptions and adding search_tools)
- **User Story 3 (Phase 5)**: Depends on Phase 2 — can proceed in parallel with Phase 3 and Phase 4
- **Polish (Phase 6)**: Depends on all user story phases complete

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — no story dependencies
- **US2 (P2)**: Depends on US1 — description audit and search_tools registration require existing tool registry
- **US3 (P3)**: Can start after Phase 2 — independent of US1 and US2 (HTTP transport is a separate concern from tool content)

### Parallel Opportunities

- Within Phase 3: T007, T008, T009, T010, T011, T012 can all run in parallel (different files, no shared state)
- Within Phase 4: T016 and T017 can run in parallel
- US3 (Phase 5) can run in parallel with US1 (Phase 3) after Phase 2 completes
- Polish tasks T021, T022, T024 can run in parallel

---

## Parallel Example: User Story 1 (Phase 3)

```bash
# All six tool module tasks can run in parallel (different files):
Task T007: "Create app/mcp/tools/workspaces.py"
Task T008: "Create app/mcp/tools/ingest.py"
Task T009: "Create app/mcp/tools/query.py"
Task T010: "Create app/mcp/tools/wiki.py"
Task T011: "Create app/mcp/tools/sources.py"
Task T012: "Create app/mcp/tools/quality.py"

# Then sequentially:
Task T013: "Register all tools in app/mcp/server.py" (depends on T007–T012)
Task T014: "Update .claude/mcp-context-wiki.sh"
Task T015: "Update .mcp.json"
```

## Parallel Example: US3 alongside US1

```bash
# After Phase 2 completes, start both simultaneously:
Developer A → Phase 3 (T007–T015): Tool surface
Developer B → Phase 5 (T019–T020): HTTP transport (server.py FastMCP instance ready from T005)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T006) — **do not skip**
3. Complete Phase 3: User Story 1 (T007–T015)
4. **STOP and VALIDATE**: Connect Claude Code, run a list-workspaces + query-wiki task, confirm ≤ 2 tool calls
5. Ship US1 — existing users immediately benefit from smaller tool surface

### Incremental Delivery

1. Setup + Foundational → skeleton ready
2. Add US1 (13 tools, stdio migration) → validate → **MVP shippable**
3. Add US2 (description audit + search_tools) → validate token reduction
4. Add US3 (HTTP transport) → validate remote access → full blog-post compliance
5. Polish → clean tests + logging → merge

### Parallel Team Strategy

With two developers after Phase 2:

- **Dev A**: Phase 3 (US1) — 6 tool files in parallel, then registration + config updates
- **Dev B**: Phase 5 (US3) — HTTP transport mount and auth; then pick up Phase 4 (US2) after Dev A finishes Phase 3

---

## Notes

- `[P]` tasks = different files, no shared write dependencies — safe to run simultaneously
- `[US1/2/3]` label maps each task to its user story for traceability
- Each user story phase ends with an explicit checkpoint — verify before moving on
- No database migrations required for this feature
- The auth proxy (`tools/mcp_auth_proxy.py`) is **not modified** — it continues to serve the stdio path
- Kiro's `.kiro/settings/mcp.json` is **not modified** in this feature — it picks up the new tool surface automatically via the existing proxy
