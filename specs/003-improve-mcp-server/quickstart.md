# Quickstart: Improve MCP Server with Anthropic Best Practices

**For**: Developers implementing feature 003  
**Date**: 2026-04-23

## What's Being Built

A purpose-built Python MCP server (replacing the `@ivotoby/openapi-mcp-server` npm bridge) with:
- 13 intent-focused tools (down from ~70 auto-generated)
- Streamable HTTP transport at `POST /mcp` for cloud agents
- Existing stdio transport maintained for Claude Code / Kiro

## File Layout

```
app/
└── mcp/
    ├── __init__.py
    ├── server.py               # FastMCP instance + tool registration
    ├── response.py             # MCPResponse envelope + serialization
    └── tools/
        ├── __init__.py
        ├── workspaces.py       # list_workspaces, get_workspace_status
        ├── ingest.py           # ingest_url, ingest_file, get_ingest_status
        ├── query.py            # query_wiki
        ├── wiki.py             # list/get/create/update wiki pages
        ├── sources.py          # list_sources
        └── quality.py          # trigger_lint

tests/
└── unit/
    └── test_mcp_tools.py       # unit tests for tool handlers

.claude/
└── mcp-context-wiki.sh         # updated: runs python -m app.mcp.server --stdio

pyproject.toml                  # add: mcp>=1.25,<2
app/main.py                     # updated: mount MCP HTTP transport at /mcp
```

## Key Implementation Notes

### Tool Handler Pattern

Each tool function:
1. Receives typed parameters (FastMCP injects them)
2. Calls the existing service/API layer directly (same process, no HTTP hop)
3. Returns a serialized `MCPResponse` as a string

```python
# Pattern for all tool handlers
from app.mcp.response import MCPResponse

async def ingest_url(workspace_id: str, url: str, title: str | None = None) -> str:
    # validate inputs
    # call service layer
    # return MCPResponse(summary="...", data={...}).to_json()
```

### Auth on HTTP Transport

The `/mcp` FastAPI route uses the same `get_current_user` dependency as all other routes. The auth proxy (`tools/mcp_auth_proxy.py`) continues to handle token injection for the stdio path — no changes needed there.

### No New Migrations

No database schema changes. All tools read/write via existing models and service functions.

### Backwards Compatibility

`.claude/mcp-context-wiki.sh` and `.mcp.json` are updated to call the Python server instead of `npx`. Existing Claude Code users reconnect automatically on next session. Kiro's `.kiro/settings/mcp.json` continues to point to the proxy and gets the new tool surface without config changes.

## Running Locally

```bash
# Start full stack (includes new MCP HTTP endpoint at :8000/mcp)
make up

# Test stdio transport (same as Claude Code uses)
python -m app.mcp.server

# Test HTTP transport — unauthenticated (expect 401)
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
# → 401

# Test HTTP transport — authenticated (expect tool list)
TOKEN=$(curl -s http://localhost:8000/api/v1/status/bootstrap | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
# → {"result":{"tools":[...]}} with ≤15 tools
```

## Running Tests

```bash
# Unit tests for MCP tools (no DB, no external services)
pytest tests/unit/test_mcp_tools.py -v

# Full test suite
make test
```
