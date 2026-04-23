import base64
import uuid

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.mcp.response import MCPResponse
from app.mcp.server import get_mcp_service_user, mcp
from app.models.ingest_job import IngestJob

logger = get_logger(__name__)


@mcp.tool(
    description=(
        "Ingests a web URL into a workspace wiki. Creates the source, queues the ingest job, "
        "and returns the job ID to track progress. Wiki pages are updated asynchronously — "
        "use get_ingest_status to poll for completion. Typical ingest takes 2-5 minutes."
    )
)
async def ingest_url(workspace_id: str, url: str, title: str = "") -> str:
    logger.info("mcp_tool_call", tool="ingest_url", workspace_id=workspace_id)
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return MCPResponse.err(f"Invalid workspace_id: {workspace_id!r}").to_json()
    if not url.startswith(("http://", "https://")):
        return MCPResponse.err("URL must start with http:// or https://").to_json()

    try:
        async with AsyncSessionLocal() as db:
            from app.api.v1.sources import UrlSourceCreate, ingest_from_url
            from app.workers.ingest_worker import process_ingest_job

            user = await get_mcp_service_user(db)
            body = UrlSourceCreate(url=url, title=title or url)
            source = await ingest_from_url(ws_uuid, body, current_user=user, db=db)

            job = IngestJob(
                workspace_id=ws_uuid,
                source_ids=[source.id],
                status="queued",
                triggered_by=user.id,
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)

            task = process_ingest_job.apply_async(args=[str(job.id)], queue="ingest")
            job.celery_task_id = task.id
            await db.commit()

        return MCPResponse(
            summary=f"Ingest job queued for '{source.title}'. Job ID: {job.id}. "
                    "Check status with get_ingest_status.",
            data={
                "source_id": str(source.id),
                "job_id": str(job.id),
                "status": "queued",
                "message": "Wiki pages will be created or updated in ~2-5 minutes.",
            },
        ).to_json()
    except Exception as exc:
        logger.info("mcp_tool_error", tool="ingest_url", error=str(exc))
        return MCPResponse.err(f"Failed to ingest URL: {exc}").to_json()


@mcp.tool(
    description=(
        "Uploads and ingests a file (PDF or plain text) into a workspace wiki. "
        "Handles upload, source creation, and job queuing. "
        "content_base64 must be the base64-encoded file bytes. "
        "Returns job ID for progress tracking via get_ingest_status."
    )
)
async def ingest_file(
    workspace_id: str, filename: str, content_base64: str, title: str = ""
) -> str:
    logger.info("mcp_tool_call", tool="ingest_file", workspace_id=workspace_id)
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return MCPResponse.err(f"Invalid workspace_id: {workspace_id!r}").to_json()
    try:
        file_bytes = base64.b64decode(content_base64)
    except Exception:
        return MCPResponse.err("content_base64 is not valid base64.").to_json()

    try:
        async with AsyncSessionLocal() as db:

            from app.core.storage import get_storage
            from app.models.source import Source
            from app.workers.ingest_worker import process_ingest_job

            user = await get_mcp_service_user(db)
            content_type = "application/pdf" if filename.lower().endswith(".pdf") else "text/plain"
            storage = get_storage()
            storage_key, content_hash = await storage.upload(file_bytes, filename, content_type)

            source = Source(
                workspace_id=ws_uuid,
                title=title or filename,
                source_type="pdf" if content_type == "application/pdf" else "text",
                storage_key=storage_key,
                content_hash=content_hash,
                byte_size=len(file_bytes),
                ingest_status="pending",
                created_by=user.id,
            )
            db.add(source)
            await db.flush()

            job = IngestJob(
                workspace_id=ws_uuid,
                source_ids=[source.id],
                status="queued",
                triggered_by=user.id,
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)

            task = process_ingest_job.apply_async(args=[str(job.id)], queue="ingest")
            job.celery_task_id = task.id
            await db.commit()

        return MCPResponse(
            summary=f"File '{filename}' uploaded and ingest job queued. Job ID: {job.id}.",
            data={
                "source_id": str(source.id),
                "job_id": str(job.id),
                "status": "queued",
                "message": "Wiki pages will be created or updated in ~2-5 minutes.",
            },
        ).to_json()
    except Exception as exc:
        logger.info("mcp_tool_error", tool="ingest_file", error=str(exc))
        return MCPResponse.err(f"Failed to ingest file: {exc}").to_json()


@mcp.tool(
    description=(
        "Polls the status of an ingest job. Returns current status "
        "(pending/running/completed/failed), pages touched, and cost. "
        "Use after calling ingest_url or ingest_file to track when ingestion completes."
    )
)
async def get_ingest_status(workspace_id: str, job_id: str) -> str:
    logger.info("mcp_tool_call", tool="get_ingest_status", workspace_id=workspace_id, job_id=job_id)
    try:
        ws_uuid = uuid.UUID(workspace_id)
        job_uuid = uuid.UUID(job_id)
    except ValueError as exc:
        return MCPResponse.err(f"Invalid UUID: {exc}").to_json()

    try:
        async with AsyncSessionLocal() as db:
            job = await db.get(IngestJob, job_uuid)
            if not job or job.workspace_id != ws_uuid:
                return MCPResponse.err(f"Ingest job {job_id} not found.").to_json()

        pages_count = len(job.pages_touched) if job.pages_touched else None
        return MCPResponse(
            summary=(
                f"Ingest job {job_id[:8]}… is {job.status}."
                + (f" Touched {pages_count} page(s)." if pages_count else "")
            ),
            data={
                "job_id": str(job.id),
                "status": job.status,
                "pages_touched": pages_count,
                "llm_cost_usd": job.llm_cost_usd,
                "error_message": job.error_message,
            },
        ).to_json()
    except Exception as exc:
        logger.info("mcp_tool_error", tool="get_ingest_status", error=str(exc))
        return MCPResponse.err(f"Failed to get ingest status: {exc}").to_json()
