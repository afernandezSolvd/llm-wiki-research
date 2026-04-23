# Implementation Plan: Improve MCP Server with Anthropic Best Practices

**Branch**: `003-improve-mcp-server` | **Date**: 2026-04-23 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/003-improve-mcp-server/spec.md`

## Summary

Replace the `@ivotoby/openapi-mcp-server` npm bridge (which auto-generates ~70 tools from the OpenAPI spec) with a purpose-built Python MCP server using the official `mcp` SDK (FastMCP). The new server exposes 13 intent-focused tools, integrates in-process with FastAPI for Streamable HTTP transport at `POST /mcp`, and maintains full backwards compatibility for existing stdio clients. This directly implements three recommendations from Anthropic's "Building Agents that Reach Production Systems with MCP" blog post: intent-focused tool design, deferred-loading token reduction through tool count, and remote HTTP transport.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: FastAPI `>=0.111.0`, `mcp>=1.25,<2` (FastMCP included), SQLAlchemy 2.0 async (existing)  
**Storage**: PostgreSQL 16 + pgvector (existing, no schema changes)  
**Testing**: pytest + pytest-asyncio (existing)  
**Target Platform**: Linux server (Docker) + local development (macOS)  
**Project Type**: Web service (FastAPI) + MCP server (in-process)  
**Performance Goals**: Tool schema response <200ms, composite tool calls complete within upstream API SLA  
**Constraints**: Zero breaking changes for existing stdio transport; no new database migrations; `mcp` SDK ≥1.25  
**Scale/Scope**: Multiple workspaces, multiple concurrent agent sessions via HTTP transport

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. LLM Wiki Pattern | ✅ Pass | MCP is a new interface layer; ingest/query/lint pipelines unchanged |
| II. Multi-Tenant Workspace Isolation | ✅ Pass | All workspace-scoped tools pass `workspace_id`; existing RBAC middleware applies on HTTP transport |
| III. Async Worker Architecture | ✅ Pass | MCP tool handlers are async FastAPI functions; no Celery changes; `asyncio.run()` not used |
| IV. Knowledge Quality Controls | ✅ Pass | Tool calls route through existing API endpoints which enforce hallucination gate and drift monitoring |
| V. Observability & Structured Logging | ✅ Pass | Tool handlers must use `logger.info("mcp_tool_call", tool=name, workspace_id=id)` structured logging |
| VI. Test Discipline | ✅ Pass | Unit tests in `tests/unit/test_mcp_tools.py`; mock at API boundary; no DB in unit tests |

**Post-Design Re-check**: No violations introduced. The new `app/mcp/` module is a pure interface layer with no direct DB access — all persistence goes through existing service functions.

## Project Structure

### Documentation (this feature)

```text
specs/003-improve-mcp-server/
├── plan.md              # This file
├── research.md          # Phase 0 — all decisions recorded
├── data-model.md        # Phase 1 — response shapes and validation rules
├── quickstart.md        # Phase 1 — implementation guide for developers
├── contracts/
│   └── mcp-tools.md     # Phase 1 — authoritative tool contracts (13 tools)
└── tasks.md             # Phase 2 output (/speckit.tasks — not yet created)
```

### Source Code (repository root)

```text
app/
└── mcp/
    ├── __init__.py
    ├── server.py               # FastMCP instance, tool registration, transport setup
    ├── response.py             # MCPResponse envelope (summary + data + error shape)
    └── tools/
        ├── __init__.py
        ├── workspaces.py       # list_workspaces, get_workspace_status
        ├── ingest.py           # ingest_url, ingest_file, get_ingest_status
        ├── query.py            # query_wiki
        ├── wiki.py             # list_wiki_pages, get_wiki_page, create_wiki_page, update_wiki_page
        ├── sources.py          # list_sources
        └── quality.py          # trigger_lint

tests/
└── unit/
    └── test_mcp_tools.py       # unit tests (mock at API-call boundary)

# Modified files
app/main.py                     # mount MCP Streamable HTTP transport at /mcp
pyproject.toml                  # add mcp>=1.25,<2 dependency
.claude/mcp-context-wiki.sh     # update stdio to: python -m app.mcp.server --stdio
.mcp.json                       # update stdio command
```

**Structure Decision**: Single-project layout. The `app/mcp/` module is a new sub-package alongside `app/api/`, `app/workers/`, etc. No new top-level directories needed — this feature is a new interface module, not a new service.

## Complexity Tracking

> No constitution violations. Table omitted.
