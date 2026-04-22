#!/usr/bin/env bash
# MCP server wrapper — routes all requests through the auth proxy which
# handles token refresh automatically. No credentials needed here.

PROXY="http://localhost:8001"
RETRIES=20

for i in $(seq 1 $RETRIES); do
  if curl -sf "${PROXY}/health" > /dev/null 2>&1; then
    break
  fi
  if [ "$i" = "$RETRIES" ]; then
    echo "[mcp-context-wiki] ERROR: auth proxy not ready after ${RETRIES} attempts" >&2
    exit 1
  fi
  echo "[mcp-context-wiki] waiting for auth proxy... (${i}/${RETRIES})"
  sleep 3
done

exec npx -y @ivotoby/openapi-mcp-server \
  --openapi-spec "${PROXY}/openapi.json" \
  --api-base-url "${PROXY}" \
  --name "context-wiki" \
  --transport stdio
