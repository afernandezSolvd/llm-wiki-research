# MCP Tool Contracts

**Version**: 1.0 | **Date**: 2026-04-23  
**Transport**: stdio + Streamable HTTP (`POST /mcp`)  
**Auth**: Bearer token (all tools require authentication)

This document is the authoritative contract for all 13 MCP tools exposed by the Context Wiki MCP server. Each tool entry defines: name, description (as shown to agents), required input parameters, and output shape reference.

---

## Workspace Tools

### `list_workspaces`

**Description**: Returns all workspaces the authenticated user is a member of. Use this first when you don't know the workspace_id. Returns workspace IDs, slugs, and display names.

**Input**: *(none)*

**Output**: `WorkspaceItem[]` — see data-model.md

---

### `get_workspace_status`

**Description**: Returns a health summary for a workspace: quality metrics (total pages, drift count), active ingest/lint jobs, and component health (API, workers, database). Use this to check if a workspace is healthy before running expensive operations, or to monitor in-progress jobs.

**Input**:
| Parameter | Type | Required | Description |
|---|---|---|---|
| `workspace_id` | UUID string | Yes | Target workspace |

**Output**: `WorkspaceStatus` — see data-model.md

---

## Ingest Tools

### `ingest_url`

**Description**: Ingests a web URL into a workspace wiki. Creates the source, queues the ingest job, and returns the job ID to track progress. The wiki pages will be created or updated asynchronously — use `get_ingest_status` to poll for completion. Typical ingest takes 2-5 minutes.

**Input**:
| Parameter | Type | Required | Description |
|---|---|---|---|
| `workspace_id` | UUID string | Yes | Target workspace |
| `url` | string | Yes | Full URL to ingest (must be http/https) |
| `title` | string | No | Display title for the source; defaults to page title if omitted |

**Output**: `IngestResult` — see data-model.md

---

### `ingest_file`

**Description**: Uploads and ingests a file (PDF or plain text) into a workspace wiki. Handles the full pipeline: upload, source creation, and job queuing. Returns job ID for progress tracking via `get_ingest_status`.

**Input**:
| Parameter | Type | Required | Description |
|---|---|---|---|
| `workspace_id` | UUID string | Yes | Target workspace |
| `filename` | string | Yes | Original filename including extension (.pdf or .txt) |
| `content_base64` | string | Yes | Base64-encoded file content |
| `title` | string | No | Display title; defaults to filename |

**Output**: `IngestResult` — see data-model.md

---

### `get_ingest_status`

**Description**: Polls the status of an ingest job. Returns current status (pending/running/completed/failed), pages touched count, and cost. Use this after calling `ingest_url` or `ingest_file` to track when ingestion is complete.

**Input**:
| Parameter | Type | Required | Description |
|---|---|---|---|
| `workspace_id` | UUID string | Yes | Target workspace |
| `job_id` | UUID string | Yes | Job ID from ingest_url or ingest_file response |

**Output**: `IngestJobStatus` — see data-model.md

---

## Query Tool

### `query_wiki`

**Description**: Asks a natural-language question against the wiki and returns a synthesized answer with citations. Uses hybrid retrieval (semantic search + knowledge graph traversal). This is the primary tool for accessing knowledge stored in the wiki — prefer it over reading individual wiki pages directly.

**Input**:
| Parameter | Type | Required | Description |
|---|---|---|---|
| `workspace_id` | UUID string | Yes | Target workspace |
| `question` | string | Yes | Natural-language question |
| `top_k` | integer | No | Number of context chunks to retrieve (default 20) |
| `user_context` | string | No | Additional context about the user's role or intent; shapes the answer framing |

**Output**: `QueryResult` — see data-model.md

---

## Wiki Page Tools

### `list_wiki_pages`

**Description**: Lists wiki pages in a workspace, optionally filtered by path prefix. Returns page paths, titles, and last-updated timestamps. Use this to discover what topics the wiki covers before reading specific pages.

**Input**:
| Parameter | Type | Required | Description |
|---|---|---|---|
| `workspace_id` | UUID string | Yes | Target workspace |
| `prefix` | string | No | Filter to pages whose path starts with this prefix (e.g., "concepts/") |

**Output**: `WikiPageItem[]` — see data-model.md

---

### `get_wiki_page`

**Description**: Retrieves the full Markdown content of a single wiki page. Use when you need the exact current content of a known page, or when `query_wiki` points to a specific page worth reading in full.

**Input**:
| Parameter | Type | Required | Description |
|---|---|---|---|
| `workspace_id` | UUID string | Yes | Target workspace |
| `page_path` | string | Yes | Relative page path (e.g., "concepts/llm-wiki-pattern.md") |

**Output**: `WikiPage` — see data-model.md

---

### `create_wiki_page`

**Description**: Creates a new wiki page with the provided Markdown content. The page is committed to the workspace's git repository. Use when adding new knowledge that doesn't map to an existing page — prefer `update_wiki_page` if the page already exists.

**Input**:
| Parameter | Type | Required | Description |
|---|---|---|---|
| `workspace_id` | UUID string | Yes | Target workspace |
| `page_path` | string | Yes | Relative path for the new page (e.g., "concepts/new-topic.md") |
| `content` | string | Yes | Full Markdown content |

**Output**: `WikiPageMutationResult` — see data-model.md

---

### `update_wiki_page`

**Description**: Updates an existing wiki page with new Markdown content. Commits the change to git. Use when you have new information that expands or corrects an existing page — the full new content replaces the existing content.

**Input**:
| Parameter | Type | Required | Description |
|---|---|---|---|
| `workspace_id` | UUID string | Yes | Target workspace |
| `page_path` | string | Yes | Relative path of the page to update |
| `content` | string | Yes | Full new Markdown content (replaces existing) |

**Output**: `WikiPageMutationResult` — see data-model.md

---

## Source Tool

### `list_sources`

**Description**: Lists all ingested sources in a workspace: URLs and uploaded files that have been processed. Returns source IDs, titles, types, and ingest timestamps. Use to see what content has already been ingested before adding duplicates.

**Input**:
| Parameter | Type | Required | Description |
|---|---|---|---|
| `workspace_id` | UUID string | Yes | Target workspace |

**Output**: `SourceItem[]` — see data-model.md

---

## Quality Tool

### `trigger_lint`

**Description**: Queues a lint run for a workspace. Lint checks for orphan pages, semantic drift, and contradictions across wiki pages. Returns a run ID. Lint runs typically complete in 1-10 minutes depending on wiki size. Use `get_workspace_status` to monitor progress.

**Input**:
| Parameter | Type | Required | Description |
|---|---|---|---|
| `workspace_id` | UUID string | Yes | Target workspace |

**Output**: `LintRunResult` — see data-model.md

---

## Meta Tool (Stretch Goal)

### `search_tools`

**Description**: Returns the full input schema and description for MCP tools matching the search query. Use this to discover tool parameter details without loading all tool schemas upfront. For example, `search_tools("ingest")` returns full schemas for ingest_url, ingest_file, and get_ingest_status.

**Input**:
| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | Yes | Keyword or phrase to match against tool names and descriptions |

**Output**: `ToolSchemaResult[]` — see data-model.md

---

## Transport Endpoints

| Transport | Endpoint | Use Case |
|---|---|---|
| stdio | `python -m app.mcp.server --stdio` | Local development (Claude Code, Kiro) |
| Streamable HTTP | `POST /mcp` | Cloud agents, CI pipelines, remote clients |

## Breaking Change Policy

Removing or renaming a tool is a breaking change. Adding new tools and new optional parameters to existing tools are non-breaking. The tool name list above is the v1.0 surface — changes increment the contract version.
