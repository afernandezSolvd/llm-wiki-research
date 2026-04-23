#!/usr/bin/env bash
# MCP server wrapper — waits for the auth proxy (confirms full stack is up),
# then runs the purpose-built Python MCP server over stdio.

PROXY="http://localhost:8001"
RETRIES=20

for i in $(seq 1 $RETRIES); do
  if curl -sf "${PROXY}/health" > /dev/null 2>&1; then
    break
  fi
  if [ "$i" = "$RETRIES" ]; then
    echo "[mcp-context-wiki] ERROR: stack not ready after ${RETRIES} attempts" >&2
    exit 1
  fi
  echo "[mcp-context-wiki] waiting for stack... (${i}/${RETRIES})"
  sleep 3
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec docker compose -f "${REPO_ROOT}/docker-compose.yml" exec -T api python -m app.mcp.server
