# Feature Specification: Improve MCP Server with Anthropic Best Practices

**Feature Branch**: `003-improve-mcp-server`  
**Created**: 2026-04-23  
**Status**: Draft  
**Input**: User description: "improve the mcp using the recommendations that Anthropic made in the blog post about building agents that reach production systems with MCP"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Intent-Focused Tool Surface (Priority: P1)

A developer using an AI agent (Claude Code, Kiro, or a custom agent) asks the wiki to do something meaningful — "ingest this URL", "query what we know about X", "show me workspace quality". Today the agent sees ~70 auto-generated tools from the raw OpenAPI mirror and must figure out which endpoints to chain. After this change, the agent sees a small set of purpose-built tools where one call does the full job.

**Why this priority**: The blog post identifies this as the highest-impact change: "fewer well-described tools outperform exhaustive API mirrors." The current `@ivotoby/openapi-mcp-server` bridge creates exactly this anti-pattern. Fixing it directly improves agent reliability and reduces unnecessary API calls.

**Independent Test**: Configure a Claude Code session with only the new MCP and ask it to "ingest a URL and query what it learned." If the agent completes the task in ≤ 2 tool calls without manual orchestration, this story passes.

**Acceptance Scenarios**:

1. **Given** an agent session with the new MCP, **When** a user asks to ingest a URL into a workspace, **Then** the agent invokes a single `ingest_url` tool and receives a structured job status response — no manual chaining of source creation, ingest trigger, and job polling endpoints.

2. **Given** an agent session, **When** a user asks "what does the wiki know about authentication?", **Then** the agent invokes `query_wiki` with the natural-language question and receives a formatted answer with citations — no manual workspace lookup, embedding search, and result assembly.

3. **Given** a tool call that succeeds, **When** the response arrives, **Then** it contains a human-readable `summary` field alongside structured data, so the agent can report progress without further parsing.

4. **Given** the total number of tools exposed by the MCP is counted, **When** the server starts, **Then** it exposes ≤ 15 tools (down from ~70+ OpenAPI mirror endpoints).

---

### User Story 2 - Deferred Tool Loading (Priority: P2)

An AI agent connects to the MCP server and only loads the full schemas for tools it actually needs, rather than pulling all definitions into context on startup. The blog post reports this reduces tool-definition token usage by 85%+ while maintaining selection accuracy.

**Why this priority**: The current setup loads every tool definition at connection time. With 70+ auto-generated tools, this burns significant context window before any real work begins. Fixing this extends how many turns an agent can work before hitting context limits.

**Independent Test**: Measure the token count of the initial tool manifest before vs. after. Passes if initial manifest tokens decrease by ≥ 50% and task completion on a 10-question benchmark remains ≥ 95%.

**Acceptance Scenarios**:

1. **Given** a fresh MCP connection, **When** the agent receives the initial tool list, **Then** it contains only lightweight stubs (name + one-line description), not full parameter schemas.

2. **Given** the agent needs to call a specific tool, **When** it fetches the full schema for that tool on demand, **Then** the schema is returned and the call succeeds.

3. **Given** an agent working on a query-only task, **When** it connects to the MCP, **Then** it never loads the schemas for ingest or admin tools, keeping those tokens out of context entirely.

---

### User Story 3 - HTTP/Remote Transport Support (Priority: P3)

A cloud-hosted agent (e.g., an Anthropic-managed agent running in the cloud, or a CI pipeline) can connect to the Context Wiki MCP server over HTTP — not just stdio. Today the MCP only works for local clients because it runs as a stdio subprocess. Remote HTTP transport enables the server to serve web and cloud agents.

**Why this priority**: The blog post states: "A remote server is what gives you distribution — it's the only configuration that runs across web, mobile, and cloud-hosted agents." This unlocks use cases beyond local developer machines.

**Independent Test**: Point a remote Claude agent at the MCP's HTTP endpoint and successfully run a `query_wiki` call without any local process on the developer's machine.

**Acceptance Scenarios**:

1. **Given** the MCP server is running, **When** a remote client connects via HTTP transport, **Then** it receives a valid MCP handshake and can list available tools.

2. **Given** a remote HTTP client with a valid bearer token, **When** it calls any MCP tool, **Then** the call is authenticated and returns a correct response.

3. **Given** an existing stdio client (Claude Code), **When** the HTTP transport is added, **Then** the stdio transport continues to work without modification — backwards compatibility is preserved.

4. **Given** an unauthenticated remote client, **When** it attempts to connect via HTTP, **Then** it receives a clear authentication error and is not granted access.

---

### Edge Cases

- What happens when the auth proxy is down and a remote client calls the HTTP MCP endpoint?
- How does the system handle an ingest job triggered via MCP that takes longer than the client's timeout?
- What happens if an agent tries to call an old auto-generated endpoint name that no longer exists after the migration?
- How does deferred loading behave for a client that doesn't support capability negotiation?
- What happens when concurrent remote sessions from multiple cloud agents hit the same workspace simultaneously?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The MCP server MUST expose ≤ 15 intent-focused tools that map to complete user workflows (e.g., `ingest_url`, `query_wiki`, `list_workspaces`, `get_workspace_status`) rather than one tool per REST endpoint.

- **FR-002**: Each tool MUST have a rich, one-paragraph description explaining its purpose, when to use it, and what it returns — sufficient for an agent to select the correct tool without reading other tools' schemas.

- **FR-003**: The MCP server MUST support deferred tool schema loading: the initial tool list MUST contain only tool names and short descriptions; full parameter schemas MUST be fetchable on demand per tool.

- **FR-004**: The MCP server MUST expose an HTTP transport endpoint in addition to the existing stdio transport, enabling remote cloud agents to connect without a local subprocess.

- **FR-005**: All HTTP transport connections MUST be authenticated using the existing bearer token mechanism; unauthenticated remote connections MUST be rejected with a descriptive error.

- **FR-006**: Every tool response MUST include a `summary` field containing a human-readable one-sentence description of the result, so agents can report status without parsing structured fields.

- **FR-007**: The `ingest_url` tool MUST handle the full ingest workflow (source creation + job trigger + initial status) in a single tool call, returning a job ID and status.

- **FR-008**: The `query_wiki` tool MUST accept a natural-language question and return a formatted answer with inline citations, encapsulating the full hybrid retrieval pipeline.

- **FR-009**: The existing stdio transport and auth proxy MUST continue to work without breaking changes for current Claude Code and Kiro users after the migration.

- **FR-010**: The MCP server MUST be a purpose-built implementation (not a generic OpenAPI-to-MCP bridge) so tool descriptions, response shaping, and deferred loading are precisely controlled.

### Key Entities

- **MCP Tool**: A named capability with a short description (always present) and a full parameter schema (loaded on demand). Wraps one or more internal API calls into a single intent.
- **Tool Manifest**: The lightweight list returned on MCP connection — names and short descriptions only, no parameter schemas.
- **Remote Session**: An authenticated HTTP MCP session from a cloud or remote agent client.
- **Composite Tool**: A tool that orchestrates multiple internal API operations (e.g., ingest = create source + trigger job + return status) exposed as a single agent action.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An agent completing a 10-step benchmark task (mix of ingest, query, and status checks) uses ≤ 30% of the tool-related context tokens compared to the current OpenAPI-mirror setup.

- **SC-002**: The number of MCP tools exposed drops from the current count (~70+) to ≤ 15 intent-focused tools.

- **SC-003**: A cloud-hosted agent successfully connects and completes a `query_wiki` call over HTTP transport without any local process running on the developer's machine.

- **SC-004**: Existing Claude Code and Kiro users experience zero breaking changes — all current stdio workflows continue to function after the migration.

- **SC-005**: A new agent user can connect to the MCP and complete a meaningful task (ingest + query) in under 5 minutes using only the tool descriptions as guidance, with no additional documentation needed.

- **SC-006**: Agent task completion rate on a standard 5-question query benchmark is ≥ 95% with the new intent-focused tool surface (matching or exceeding the current auto-generated surface).

## Assumptions

- The existing auth proxy (`tools/mcp_auth_proxy.py`) continues to serve the stdio transport path unchanged; the new HTTP MCP endpoint sits on the main API server with the same bearer token auth.
- The new MCP server is a purpose-built Python server replacing the `@ivotoby/openapi-mcp-server` bridge for both stdio and HTTP transports.
- Deferred tool loading uses MCP protocol's native capability negotiation; clients that don't support it receive the full lightweight manifest and can still call any tool.
- Mobile and browser-based MCP clients are out of scope for v1 of the HTTP transport — the focus is cloud-hosted and CI agent runtimes.
- Backwards compatibility for Kiro (`.kiro/settings/mcp.json`) is required at the stdio level; Kiro's HTTP config update is a follow-on task.
- The 15-tool limit is a ceiling guideline; tools that serve fundamentally different user intentions count separately even if they share an underlying API endpoint.
