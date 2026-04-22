#!/usr/bin/env bash
# MCP server wrapper — auto-fetches a long-lived bootstrap token at startup.
# Retries until the API is ready (handles race at docker compose start).

API="http://localhost:8000/api/v1/status/bootstrap"
TOKEN=""
RETRIES=10

for i in $(seq 1 $RETRIES); do
  TOKEN=$(curl -sf "$API" | jq -r '.access_token // empty')
  if [ -n "$TOKEN" ]; then
    break
  fi
  sleep 3
done

if [ -z "$TOKEN" ]; then
  echo "[mcp-context-wiki] ERROR: could not fetch bootstrap token after ${RETRIES} attempts" >&2
  exit 1
fi

exec npx -y @ivotoby/openapi-mcp-server \
  --openapi-spec "http://localhost:8000/openapi.json" \
  --api-base-url "http://localhost:8000" \
  --headers "Authorization:Bearer $TOKEN" \
  --name "context-wiki" \
  --transport stdio
