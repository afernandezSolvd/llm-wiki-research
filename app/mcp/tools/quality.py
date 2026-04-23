import uuid

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.mcp.response import MCPResponse
from app.mcp.server import get_mcp_service_user, mcp

logger = get_logger(__name__)


@mcp.tool(
    description=(
        "Queues a lint run for a workspace to check for orphan pages, "
        "semantic drift, and contradictions. "
        "Returns a run ID. Lint typically completes in 1-10 minutes. "
        "Use get_workspace_status to monitor progress."
    )
)
async def trigger_lint(workspace_id: str) -> str:
    logger.info("mcp_tool_call", tool="trigger_lint", workspace_id=workspace_id)
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return MCPResponse.err(f"Invalid workspace_id: {workspace_id!r}").to_json()

    try:
        async with AsyncSessionLocal() as db:
            from app.models.lint_run import LintRun
            from app.workers.lint_worker import process_lint_run

            user = await get_mcp_service_user(db)
            run = LintRun(
                workspace_id=ws_uuid,
                scope="full",
                triggered_by=user.id,
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)

            task = process_lint_run.apply_async(args=[str(run.id)], queue="lint")
            run.celery_task_id = task.id
            await db.commit()

        return MCPResponse(
            summary=f"Lint run queued. Run ID: {run.id}. Check progress with get_workspace_status.",
            data={"run_id": str(run.id), "status": "queued"},
        ).to_json()
    except Exception as exc:
        logger.info("mcp_tool_error", tool="trigger_lint", error=str(exc))
        return MCPResponse.err(f"Failed to trigger lint: {exc}").to_json()
