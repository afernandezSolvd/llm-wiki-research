Ingest a source file or URL into the wiki system.

Usage: /ingest <file_path_or_url> [workspace_id]

Steps:
1. Determine if $0 is a local file path or a URL (starts with http).

If local file:
2a. Upload it via multipart POST to /api/v1/workspaces/$WS_ID/sources
    - file field: the file contents
    - title field: derived from the filename (strip extension, replace hyphens/underscores with spaces)
    - Set Authorization: Bearer $CONTEXT_API_TOKEN

If URL:
2b. POST /api/v1/workspaces/$WS_ID/sources/from-url
    Body: {"url": "<url>", "title": "<derived from URL path or domain>"}

3. From the response, extract the source "id".

4. Trigger ingest:
   POST /api/v1/workspaces/$WS_ID/ingest
   Body: {"source_ids": ["<source_id>"]}
   This returns 202 Accepted with a job id.

5. Poll GET /api/v1/workspaces/$WS_ID/ingest/<job_id> every 5 seconds
   until status is "done" or "failed" (timeout after 5 minutes).

6. Report outcome:
   - If done: show pages_touched count, llm_tokens_used, llm_cost_usd
   - If failed: show error_message and suggest: docker compose logs worker --tail=50

Use $CONTEXT_API_TOKEN for auth. Use $WS_ID as workspace, or $1 if provided.
If neither is set, ask the user for their token and workspace ID.
