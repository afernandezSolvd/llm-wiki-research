# Data Model: Documentation & Sources Browser GUI

**Phase 1 output** | Feature: 002-docs-browser-gui | Date: 2026-04-22

---

## Overview

This feature adds no new database tables. It exposes a read-only subset of four existing models through the new public API layer, plus one new query pattern (full-text search) against existing data.

---

## Entities Exposed (read-only)

### Workspace

**Source model**: `app/models/workspace.py` → `Workspace`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Primary key |
| `slug` | string | URL-safe unique name |
| `display_name` | string | Human-readable name |
| `schema_version` | int | Schema revision counter |

**Public API projection** (`WorkspacePublicResponse`):

```
id, slug, display_name, schema_version
```

No new fields. Identical to `WorkspaceResponse` minus any future auth-only fields.

---

### WikiPage (list view)

**Source model**: `app/models/wiki.py` → `WikiPage`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Primary key |
| `page_path` | string | Unique path within workspace (e.g. `company/overview`) |
| `title` | string | Display title |
| `page_type` | string | Category/type label |
| `word_count` | int\|null | Populated after ingest |
| `updated_at` | datetime\|null | Last write timestamp |

**Public API projection** (`WikiPagePublicResponse`): identical to existing `WikiPageResponse`.

---

### WikiPageDetail (single page)

**Source model**: `WikiPage.content` (from git or DB)

Adds `content: str` (full Markdown text) to the list projection.

**Public API projection** (`WikiPageDetailPublicResponse`): identical to existing `WikiPageDetail`.

---

### Source

**Source model**: `app/models/source.py` → `Source`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Primary key |
| `title` | string | Display name / filename / URL |
| `source_type` | enum | `pdf`, `url`, `text`, `docx`, `image` |
| `ingest_status` | enum | `pending`, `ingesting`, `completed`, `failed` |
| `byte_size` | int\|null | File size in bytes |
| `created_at` | datetime | Upload/creation time |

**Public API projection** (`SourcePublicResponse`): adds `created_at` to the existing `SourceResponse` (omitted from the original schema; needed for FR-004).

---

### Source → Pages Map

**Source model**: `app/models/wiki.py` → `WikiPageSourceMap`

| Field | Type | Notes |
|-------|------|-------|
| `wiki_page_id` | UUID | FK → `WikiPage.id` |
| `source_id` | UUID | FK → `Source.id` |

**Public API projection** (`SourcePagesResponse`): returns a list of `WikiPagePublicResponse` records that originated from a given source.

---

## New Query: Full-Text Search

**No new model**. The search endpoint queries the existing `WikiPage` table:

```sql
SELECT id, page_path, title, page_type, word_count, updated_at,
       LEFT(content, 300) AS snippet
FROM wiki_pages
WHERE workspace_id = :workspace_id
  AND (title ILIKE '%' || :q || '%' OR content ILIKE '%' || :q || '%')
ORDER BY
  CASE WHEN title ILIKE '%' || :q || '%' THEN 0 ELSE 1 END,
  updated_at DESC
LIMIT 20;
```

**Search result projection** (`SearchResultItem`):

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Page ID |
| `page_path` | string | For link construction |
| `title` | string | Display in results list |
| `snippet` | string | First ~300 chars of content (or context around match) |
| `updated_at` | datetime\|null | For freshness display |

---

## New Pydantic Schemas Required

All in `app/api/v1/public.py` (inline, since these are portal-only projections):

- `WorkspacePublicResponse`
- `WikiPagePublicResponse`
- `WikiPageDetailPublicResponse`
- `SourcePublicResponse` (adds `created_at`)
- `SourcePagesResponse`
- `SearchResultItem`
- `SearchResponse` (wraps list of `SearchResultItem` + `total_count`)

---

## No Migrations Required

No schema changes. No new tables, columns, or indexes. The ILIKE search operates on existing `content` and `title` columns. Performance is acceptable up to ~500 pages per the success criterion (SC-004); a `tsvector` index can be added in a follow-on migration if needed for larger workspaces.
