# Data Model: Improve MCP Server

**Phase**: 1 | **Date**: 2026-04-23

## Summary

No new database tables or columns are required. The MCP server is a pure interface layer over existing data. This document describes the **in-memory data shapes** (Pydantic models) used by MCP tool handlers.

---

## MCP Response Envelope

All MCP tool responses are serialized as JSON strings in the MCP text content field using this envelope:

```
MCPResponse
├── summary: str          — one-sentence human-readable outcome
└── data: dict            — structured payload (tool-specific, see below)
```

---

## Tool-Specific Response Shapes

### `list_workspaces` → `data`
```
WorkspaceItem[]
├── id: UUID
├── slug: str
├── display_name: str
└── schema_version: int
```

### `get_workspace_status` → `data`
```
WorkspaceStatus
├── workspace_id: UUID
├── quality: QualityReport     — from /status/quality
│   ├── total_pages: int
│   ├── pages_with_drift: int
│   └── drift_severity: "ok" | "warning" | "error"
├── active_jobs: JobSummary[]  — from /status/jobs
│   ├── id: UUID
│   ├── type: str
│   └── status: str
└── components: ComponentHealth[]   — from /status/components
    ├── name: str
    └── healthy: bool
```

### `ingest_url` / `ingest_file` → `data`
```
IngestResult
├── source_id: UUID
├── job_id: UUID
├── status: str              — "pending" | "running"
└── message: str             — human context (e.g., "job queued, ~2-5 min")
```

### `get_ingest_status` → `data`
```
IngestJobStatus
├── job_id: UUID
├── status: str              — "pending" | "running" | "completed" | "failed"
├── pages_touched: int | null
├── llm_cost_usd: float | null
└── error_message: str | null
```

### `query_wiki` → `data`
```
QueryResult
├── answer: str
├── citations: Citation[]
│   ├── title: str
│   └── page_path: str
├── tokens_used: int
└── cost_usd: float
```

### `list_wiki_pages` → `data`
```
WikiPageItem[]
├── page_path: str
├── title: str
└── updated_at: str (ISO 8601)
```

### `get_wiki_page` → `data`
```
WikiPage
├── page_path: str
├── title: str
├── content: str        — full Markdown content
└── updated_at: str
```

### `create_wiki_page` / `update_wiki_page` → `data`
```
WikiPageMutationResult
├── page_path: str
├── action: "created" | "updated"
└── commit_sha: str | null
```

### `list_sources` → `data`
```
SourceItem[]
├── id: UUID
├── title: str
├── source_type: str     — "url" | "upload"
├── url: str | null
└── ingested_at: str | null
```

### `trigger_lint` → `data`
```
LintRunResult
├── run_id: UUID
└── status: str          — "queued"
```

### `search_tools` → `data` (stretch goal)
```
ToolSchemaResult[]
├── name: str
├── description: str
└── input_schema: dict    — full JSON Schema for this tool
```

---

## Validation Rules

- `workspace_id` on all workspace-scoped tools is validated as UUID; non-UUID input returns a structured error in `summary` before any API call.
- `url` in `ingest_url` must start with `http://` or `https://`; validated before dispatch.
- `page_path` in wiki tools must be a relative path (no leading `/`); normalized if leading slash is present.
- `content` in `create_wiki_page` / `update_wiki_page` must be non-empty string.

---

## Error Shape

When a tool call fails, the same envelope is used:

```
MCPResponse
├── summary: str    — human-readable error: "Failed to ingest URL: workspace not found"
└── data:
    ├── error: str  — machine-readable error code
    └── detail: str — full error message from upstream
```
