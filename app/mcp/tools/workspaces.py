import uuid

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.mcp.response import MCPResponse
from app.mcp.server import mcp
from app.models.workspace import Workspace

logger = get_logger(__name__)


@mcp.tool(
    description=(
        "Returns all workspaces the service account can access. "
        "Use this first when you don't know the workspace_id. "
        "Returns workspace IDs, slugs, and display names."
    )
)
async def list_workspaces() -> str:
    logger.info("mcp_tool_call", tool="list_workspaces")
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Workspace).where(Workspace.deleted_at.is_(None)).order_by(Workspace.created_at)
            )
            workspaces = result.scalars().all()
            items = [
                {
                    "id": str(ws.id),
                    "slug": ws.slug,
                    "display_name": ws.display_name,
                    "schema_version": ws.schema_version,
                }
                for ws in workspaces
            ]
        return MCPResponse(
            summary=f"Found {len(items)} workspace(s).",
            data={"workspaces": items},
        ).to_json()
    except Exception as exc:
        logger.info("mcp_tool_error", tool="list_workspaces", error=str(exc))
        return MCPResponse.err(f"Failed to list workspaces: {exc}").to_json()


@mcp.tool(
    description=(
        "Returns a health summary for a workspace: quality metrics (total pages, drift count), "
        "active ingest and lint jobs, and component health. "
        "Use before running expensive operations or to monitor in-progress jobs."
    )
)
async def get_workspace_status(workspace_id: str) -> str:
    logger.info("mcp_tool_call", tool="get_workspace_status", workspace_id=workspace_id)
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return MCPResponse.err(f"Invalid workspace_id: {workspace_id!r}").to_json()

    try:
        async with AsyncSessionLocal() as db:
            from app.api.v1.status import _check_components, get_jobs, get_quality
            from app.mcp.server import get_mcp_service_user
            from app.schemas.status import JobsResponse, QualityResponse

            user = await get_mcp_service_user(db)

            quality: QualityResponse = await get_quality(ws_uuid, current_user=user, db=db)
            jobs: JobsResponse = await get_jobs(ws_uuid, current_user=user, db=db)
            components = await _check_components(db)

        drift_count = len(quality.drift_alerts)
        active_jobs = [
            {"id": str(j.id), "type": j.queue, "status": j.status}
            for j in jobs.jobs
            if j.status in ("queued", "running")
        ]
        component_data = [{"name": c.name, "healthy": c.status == "healthy"} for c in components]

        summary = (
            f"Workspace has {drift_count} drift alert(s), "
            f"{len(active_jobs)} active job(s), "
            f"{sum(1 for c in components if c.status != 'healthy')} unhealthy component(s)."
        )
        return MCPResponse(
            summary=summary,
            data={
                "workspace_id": workspace_id,
                "quality": {
                    "drift_alerts": drift_count,
                    "drift_severity": (
                        "error" if any(a.severity == "error" for a in quality.drift_alerts)
                        else ("warning" if drift_count else "ok")
                    ),
                },
                "active_jobs": active_jobs,
                "components": component_data,
            },
        ).to_json()
    except Exception as exc:
        logger.info("mcp_tool_error", tool="get_workspace_status", error=str(exc))
        return MCPResponse.err(f"Failed to get workspace status: {exc}").to_json()
