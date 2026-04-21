Show a health and activity summary for the current workspace.

Usage: /wiki-status

Steps:
1. GET /api/v1/workspaces/$WS_ID/wiki/pages?limit=200
   Count total pages. Group by page_type. Sum word_count.

2. GET /api/v1/workspaces/$WS_ID/graph/communities
   Count communities and note largest by member_count.

3. GET /api/v1/workspaces/$WS_ID/graph/nodes?limit=1
   (just to get total count from response if available)

4. GET /api/v1/admin/cost-report?workspace_id=$WS_ID
   (requires platform admin token — skip gracefully if 403)

5. Format as a clean summary table:

   ## Wiki Health — <workspace_id>

   | Metric                  | Value        |
   |-------------------------|--------------|
   | Total wiki pages        | N            |
   | Entity pages            | N            |
   | Concept pages           | N            |
   | Summary pages           | N            |
   | Exploration pages       | N            |
   | Total word count        | N words      |
   | KG communities          | N            |
   | Largest community       | N members    |
   | Total LLM cost          | $N.NN        |

6. If any page_type has 0 pages, note it as a gap:
   "No concept pages yet — run /ingest to build the wiki."

Use $CONTEXT_API_TOKEN and $WS_ID from environment.
Use $CONTEXT_ADMIN_TOKEN for the cost report (falls back to $CONTEXT_API_TOKEN).
