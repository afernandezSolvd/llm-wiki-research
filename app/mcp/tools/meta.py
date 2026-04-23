from app.core.logging import get_logger
from app.mcp.response import MCPResponse
from app.mcp.server import mcp

logger = get_logger(__name__)


@mcp.tool(
    description=(
        "Returns full parameter schemas for tools matching a keyword query. "
        "Use this to discover tool details without loading all schemas upfront. "
        "Example: search_tools('ingest') returns schemas for all ingest-related tools."
    )
)
async def search_tools(query: str) -> str:
    logger.info("mcp_tool_call", tool="search_tools", query=query)
    if not query.strip():
        return MCPResponse.err("query must not be empty.").to_json()

    try:
        query_lower = query.lower()
        tools = mcp.list_tools() if hasattr(mcp, "list_tools") else []

        matches = []
        for tool in tools:
            name = getattr(tool, "name", "") or ""
            desc = getattr(tool, "description", "") or ""
            if query_lower in name.lower() or query_lower in desc.lower():
                schema = getattr(tool, "inputSchema", None) or getattr(tool, "parameters", None)
                matches.append({
                    "name": name,
                    "description": desc,
                    "input_schema": schema,
                })

        return MCPResponse(
            summary=f"Found {len(matches)} tool(s) matching '{query}'.",
            data={"tools": matches},
        ).to_json()
    except Exception as exc:
        logger.info("mcp_tool_error", tool="search_tools", error=str(exc))
        return MCPResponse.err(f"Failed to search tools: {exc}").to_json()
