import uuid

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.mcp.response import MCPResponse
from app.mcp.server import mcp

logger = get_logger(__name__)


@mcp.tool(
    description=(
        "Lists all ingested sources in a workspace: URLs and uploaded files "
        "that have been processed. "
        "Returns source IDs, titles, types, and ingest status. "
        "Use to see what content has already been ingested before adding duplicates."
    )
)
async def list_sources(workspace_id: str) -> str:
    logger.info("mcp_tool_call", tool="list_sources", workspace_id=workspace_id)
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return MCPResponse.err(f"Invalid workspace_id: {workspace_id!r}").to_json()

    try:
        async with AsyncSessionLocal() as db:
            from app.models.source import Source

            result = await db.execute(
                select(Source)
                .where(Source.workspace_id == ws_uuid)
                .order_by(Source.created_at.desc())
                .limit(100)
            )
            sources = result.scalars().all()

        items = [
            {
                "id": str(s.id),
                "title": s.title,
                "source_type": s.source_type,
                "ingest_status": s.ingest_status,
                "byte_size": s.byte_size,
            }
            for s in sources
        ]
        return MCPResponse(
            summary=f"Found {len(items)} source(s) in workspace.",
            data={"sources": items},
        ).to_json()
    except Exception as exc:
        logger.info("mcp_tool_error", tool="list_sources", error=str(exc))
        return MCPResponse.err(f"Failed to list sources: {exc}").to_json()
