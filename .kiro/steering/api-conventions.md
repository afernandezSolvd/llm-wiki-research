# API Conventions

## Authentication
All endpoints except /auth/* require:
  Authorization: Bearer <access_token>

Roles (IntEnum): reader=1 < editor=2 < admin=3
Platform admins (is_platform_admin=True) bypass all workspace role checks.

## URL Structure
All routes: /api/v1/{resource}
Workspace-scoped: /api/v1/workspaces/{workspace_id}/{resource}

## Response Codes
- 200: success (GET, PUT, PATCH)
- 201: created (POST new resource)
- 202: accepted (async jobs: ingest, lint — returns job id, client polls)
- 204: no content (DELETE)
- 409: conflict (duplicate content_hash on source upload)
- 429: rate limit exceeded (Retry-After header included)

## Error Format
All errors: {"detail": "human readable message"}

## Pagination
Endpoints with lists support: ?limit=N&offset=N
Max limit is always 200. Default varies by endpoint (50-100).
Always order results by updated_at DESC.

## Async Jobs (Ingest / Lint)
POST returns 202 with {id, status: "queued"}.
Client polls GET /{job_id} until status = "done" or "failed".
Workers are Celery tasks; results are stored in PostgreSQL.

## Rate Limits (per user per endpoint, requests/minute)
ingest: 10 | query: 60 | lint: 5 | default: 120

## Workspace Scoping
Every workspace has an isolated:
- Git repository (wiki pages as Markdown files)
- PostgreSQL rows (all models have workspace_id FK)
- Redis keys (prefixed with workspace_id)
- KG nodes and edges
Data from one workspace is never visible to another workspace's queries.
