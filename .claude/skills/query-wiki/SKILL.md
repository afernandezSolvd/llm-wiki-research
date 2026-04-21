Query the wiki and return the answer with citations.

Usage: /query-wiki <question>

Steps:
1. POST /api/v1/workspaces/$WS_ID/query
   Headers: Authorization: Bearer $CONTEXT_API_TOKEN
   Body: {
     "question": "$ARGUMENTS",
     "top_k": 20
   }

2. Display the answer. Format citations as clickable links:
   - Wiki citations: [Page Title](page_path)
   - Source citations: [Source: title]

3. Show a one-line cost summary at the bottom:
   Tokens: <N> | Cost: $<N.NNNN>

4. After the answer, if the answer contains phrases like "I don't have
   information", "not found", or "cannot find", add a tip:
   "The wiki may not have this yet. Try /ingest <relevant_document> to add
   it, or /run-lint to check for gaps."

Use $CONTEXT_API_TOKEN and $WS_ID from environment.
