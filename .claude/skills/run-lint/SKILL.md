Run a lint pass over the wiki and interactively review findings.

Usage: /run-lint [full|incremental]

Steps:
1. POST /api/v1/workspaces/$WS_ID/lint
   Headers: Authorization: Bearer $CONTEXT_API_TOKEN
   Body: {"scope": "$0" or "full" if not specified}
   Save the returned run id.

2. Poll GET /api/v1/workspaces/$WS_ID/lint/<run_id> every 5 seconds
   until status = "done" or "failed".

3. GET /api/v1/workspaces/$WS_ID/lint/<run_id>/findings

4. Group and display findings:

   ## Errors
   For each severity=error finding:
   - If finding_type=contradiction: show page_a, page_b, the two excerpts
     side by side, then ask: "Would you like me to read both pages and
     propose a resolution?"
   - If finding_type=semantic_drift: show page_path, absolute_drift,
     version_count, then ask: "Would you like to see the git history to
     find when this drifted?"

   ## Warnings
   For each severity=warning finding:
   - If finding_type=orphan: show page_path, then ask: "Should I add a
     link to this page from index.md?"
   - Other warnings: show description.

5. Show summary: N errors, N warnings across N pages.

6. If finding_count = 0: "Wiki is clean — no findings."

Use $CONTEXT_API_TOKEN and $WS_ID from environment.
