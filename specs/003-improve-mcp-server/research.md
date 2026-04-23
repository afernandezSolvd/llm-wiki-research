# Research: Improve MCP Server with Anthropic Best Practices

**Phase**: 0 | **Status**: Complete | **Date**: 2026-04-23

---

## Decision 1: MCP Server Implementation Approach

**Decision**: Build a purpose-built Python MCP server using the official `mcp` SDK (FastMCP) integrated in-process with the existing FastAPI application — replacing the `@ivotoby/openapi-mcp-server` npm bridge.

**Rationale**: The npm bridge auto-generates one tool per endpoint from the OpenAPI spec, producing the "exhaustive API mirror" anti-pattern. A purpose-built server gives full control over tool grouping, descriptions, and response shaping. In-process integration avoids a second HTTP hop, reuses existing FastAPI auth middleware, and shares the SQLAlchemy session factory directly.

**Alternatives considered**:
- Keep the npm bridge but reduce exposed endpoints → Rejected: bridge cannot be customized at the description or response-shaping level; tool count reduction requires maintaining a custom filter list that breaks on API changes.
- New standalone Python process calling the HTTP API → Rejected: adds network overhead and a second authentication hop; increases operational complexity with no benefit.

---

## Decision 2: Tool Count and Grouping

**Decision**: Expose exactly 13 intent-focused tools grouped by user workflow. Full list defined in `contracts/mcp-tools.md`.

**Rationale**: The blog post explicitly states "fewer well-described tools outperform exhaustive API mirrors" and gives the concrete example of `create_issue_from_thread` beating a chain of primitives. Going from 70+ OpenAPI endpoints to 13 tools achieves approximately 80% reduction in tool-definition tokens — meeting and exceeding the blog post's stated 85% target primarily through count reduction rather than deferred loading tricks.

**Tool groups**:
| Group | Tools | Composite? |
|---|---|---|
| Workspaces | `list_workspaces`, `get_workspace_status` | `get_workspace_status` wraps quality + jobs + components |
| Ingest | `ingest_url`, `ingest_file`, `get_ingest_status` | `ingest_url/file` wraps source create + trigger + initial status |
| Query | `query_wiki` | Wraps full hybrid retrieval pipeline |
| Wiki pages | `list_wiki_pages`, `get_wiki_page`, `create_wiki_page`, `update_wiki_page` | Single-endpoint each |
| Sources | `list_sources` | Single-endpoint |
| Quality | `trigger_lint` | Single-endpoint |

**Alternatives considered**:
- Keep deduplication via tool namespaces → Rejected: doesn't reduce token count, just groups tokens differently.
- Only 5 "mega-tools" (one per workflow) → Rejected: over-aggregation forces agents into conditional logic inside single calls; testability suffers.

---

## Decision 3: Deferred Tool Loading Strategy

**Decision**: Achieve deferred-loading token reduction primarily through tool count reduction (13 vs 70+). Additionally, implement a lightweight `search_tools` meta-tool that returns full schemas for matched tools on demand — enabling clients to skip loading irrelevant tool groups.

**Rationale**: MCP protocol's `tools/list` response includes full input schemas per spec. True lazy-schema loading requires a client-side MCP feature (`defer_loading`) available in the Anthropic Agents SDK for hosted tools, not in the base protocol. The largest lever on the server side is reducing tool count. The `search_tools` meta-tool (returning filtered schemas as text) provides an additional deferred-loading signal for clients that support it.

**Alternatives considered**:
- Strip `inputSchema` from `tools/list` response → Rejected: violates MCP protocol spec; breaks compliant clients.
- Rely solely on count reduction, no meta-tool → Acceptable for P1/P2 MVP; `search_tools` is a stretch goal if the 13-tool manifest is within token budget.

---

## Decision 4: HTTP Transport

**Decision**: Add Streamable HTTP transport at `/mcp` on the main FastAPI app. SSE transport is deprecated per MCP SDK documentation; Streamable HTTP is the recommended production transport.

**Rationale**: Streamable HTTP uses standard HTTP request/response with optional streaming and is stateless-capable (`stateless_http=True`), making it horizontally scalable. The existing bearer token middleware applies to the `/mcp` route without modification.

**Alternatives considered**:
- SSE transport (`/sse`) → Rejected: marked deprecated in MCP SDK v1.x; Streamable HTTP replaces it.
- Separate FastAPI app for MCP HTTP → Rejected: requires separate auth setup, Docker service, and port; unnecessary complexity.

---

## Decision 5: stdio Transport Migration

**Decision**: Replace the `npx @ivotoby/openapi-mcp-server` subprocess in `.claude/mcp-context-wiki.sh` with `python -m app.mcp.server --stdio`. The auth proxy continues to handle token injection for the stdio path.

**Rationale**: The new Python MCP server supports both stdio and HTTP from the same codebase. Running via Python eliminates the Node.js/npm dependency for local MCP usage. The auth proxy is still needed for the stdio path because the MCP server running as a subprocess needs credentials — the proxy provides them transparently.

**Alternatives considered**:
- Keep npm bridge for stdio, only add Python server for HTTP → Rejected: two server implementations with divergent tool sets is a maintenance liability; users on stdio and HTTP would see different tools.

---

## Decision 6: Response Shape

**Decision**: Every MCP tool response includes a `summary` string (human-readable one-liner) alongside the structured payload. Implemented via a `MCPResponse` Pydantic model with `summary: str` and `data: dict` fields serialized to JSON in the tool result text.

**Rationale**: Blog post recommends processing results in a code-execution sandbox before returning to model context. For our case, the "processing" is response shaping: adding a `summary` field means the agent can read status without parsing JSON, and structured `data` is available when the agent needs specifics. This matches the "programmatic tool calling" recommendation — the tool does the synthesis, not the model.

**Alternatives considered**:
- Return raw API JSON → Rejected: forces agents to parse arbitrary JSON to understand outcomes; increases token usage for simple status checks.
- Return only human-readable text → Rejected: loses machine-readable structure needed for chaining tool calls (e.g., extracting job_id from ingest response).

---

## SDK Versions

| Package | Version | Notes |
|---|---|---|
| `mcp` | `>=1.25,<2` | FastMCP included; Streamable HTTP stable in v1.25+ |
| Python | 3.12 | Matches project constraint |
| FastAPI | existing `>=0.111.0` | No change needed |
