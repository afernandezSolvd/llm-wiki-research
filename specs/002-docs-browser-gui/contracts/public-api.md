# Contract: Public Read-Only API

**Router prefix**: `/api/v1/public`  
**Auth**: None (no `Authorization` header required)  
**Guard**: Only active when `PUBLIC_API_ENABLED=true` (env var); returns `503` otherwise  
**Rate limit**: Inherits existing middleware; no separate limit for v1

---

## Endpoints

### List Workspaces

```
GET /api/v1/public/workspaces
```

**Response `200`**:
```json
[
  {
    "id": "uuid",
    "slug": "string",
    "display_name": "string",
    "schema_version": 0
  }
]
```

**Empty workspace list**: `[]` — not a `404`.

---

### List Wiki Pages

```
GET /api/v1/public/workspaces/{workspace_id}/pages
    ?limit=50&offset=0&page_type=<string>
```

**Path params**:
- `workspace_id` (UUID) — must be a valid workspace; returns `404` if not found.

**Query params**:
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)
- `page_type` (string, optional) — filter by page type

**Response `200`**:
```json
[
  {
    "id": "uuid",
    "page_path": "string",
    "title": "string",
    "page_type": "string",
    "word_count": 0,
    "updated_at": "2026-04-22T00:00:00Z"
  }
]
```

**Errors**: `404` workspace not found.

---

### Get Single Page

```
GET /api/v1/public/workspaces/{workspace_id}/pages/{page_path:path}
```

**Path params**:
- `workspace_id` (UUID)
- `page_path` (string, path-encoded) — e.g. `company/overview`

**Response `200`**:
```json
{
  "id": "uuid",
  "page_path": "string",
  "title": "string",
  "page_type": "string",
  "word_count": 0,
  "updated_at": "2026-04-22T00:00:00Z",
  "content": "# Markdown content here\n..."
}
```

**Errors**: `404` workspace or page not found.

---

### List Sources

```
GET /api/v1/public/workspaces/{workspace_id}/sources
    ?status_filter=<string>&limit=50&offset=0
```

**Query params**:
- `status_filter` (string, optional) — one of `pending`, `ingesting`, `completed`, `failed`
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

**Response `200`**:
```json
[
  {
    "id": "uuid",
    "title": "string",
    "source_type": "pdf|url|text|docx|image",
    "ingest_status": "pending|ingesting|completed|failed",
    "byte_size": 0,
    "created_at": "2026-04-22T00:00:00Z"
  }
]
```

**Errors**: `404` workspace not found.

---

### Get Pages Produced by a Source

```
GET /api/v1/public/workspaces/{workspace_id}/sources/{source_id}/pages
```

**Response `200`** — array of page list items (same shape as List Wiki Pages):
```json
[
  {
    "id": "uuid",
    "page_path": "string",
    "title": "string",
    "page_type": "string",
    "word_count": 0,
    "updated_at": "2026-04-22T00:00:00Z"
  }
]
```

**Errors**: `404` workspace or source not found.

---

### Search Pages

```
GET /api/v1/public/workspaces/{workspace_id}/search
    ?q=<string>&limit=20
```

**Query params**:
- `q` (string, required, min length 2) — search term
- `limit` (int, default 20, max 50)

**Response `200`**:
```json
{
  "total_count": 0,
  "results": [
    {
      "id": "uuid",
      "page_path": "string",
      "title": "string",
      "snippet": "string",
      "updated_at": "2026-04-22T00:00:00Z"
    }
  ]
}
```

**Errors**:
- `400` if `q` is missing or shorter than 2 characters.
- `404` workspace not found.

---

## Error Response Shape

All errors follow the existing FastAPI `HTTPException` pattern:

```json
{
  "detail": "string"
}
```

---

## CORS

During development, the portal dev server runs on `http://localhost:5173`. The API's `CORSMiddleware` must allow this origin when `ENVIRONMENT=development`.

In production (Nginx proxy), no CORS headers are needed because the portal and the API are behind the same Nginx reverse proxy and are served from the same origin.

---

## Structured Logging Requirements

Every public endpoint MUST emit a structured log on each request:

```python
logger.info("public_api_request", endpoint="list_pages", workspace_id=str(workspace_id))
```
