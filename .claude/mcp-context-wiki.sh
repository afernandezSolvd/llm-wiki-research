#!/usr/bin/env bash
# MCP server wrapper — auto-fetches bootstrap token so no manual setup needed
TOKEN=$(curl -s http://localhost:8000/api/v1/status/bootstrap | jq -r '.access_token')
exec npx -y @ivotoby/openapi-mcp-server \
  --openapi-spec "http://localhost:8000/openapi.json" \
  --api-base-url "http://localhost:8000" \
  --headers "Authorization:Bearer $TOKEN" \
  --name "context-wiki" \
  --transport stdio
