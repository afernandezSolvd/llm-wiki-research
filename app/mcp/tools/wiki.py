import hashlib
import uuid

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.mcp.response import MCPResponse
from app.mcp.server import get_mcp_service_user, mcp

logger = get_logger(__name__)


@mcp.tool(
    description=(
        "Lists wiki pages in a workspace, optionally filtered by path prefix. "
        "Returns page paths, titles, and last-updated timestamps. "
        "Use to discover what topics the wiki covers before reading specific pages."
    )
)
async def list_wiki_pages(workspace_id: str, prefix: str = "") -> str:
    logger.info("mcp_tool_call", tool="list_wiki_pages", workspace_id=workspace_id)
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return MCPResponse.err(f"Invalid workspace_id: {workspace_id!r}").to_json()

    try:
        async with AsyncSessionLocal() as db:
            from app.models.wiki_page import WikiPage

            q = (
                select(WikiPage)
                .where(WikiPage.workspace_id == ws_uuid)
                .order_by(WikiPage.updated_at.desc())
                .limit(200)
            )
            result = await db.execute(q)
            pages = result.scalars().all()

        if prefix:
            pages = [p for p in pages if p.page_path.startswith(prefix)]

        items = [
            {
                "page_path": p.page_path,
                "title": p.title,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in pages
        ]
        return MCPResponse(
            summary=(
                f"Found {len(items)} wiki page(s)"
                + (f" with prefix '{prefix}'" if prefix else "")
                + "."
            ),
            data={"pages": items},
        ).to_json()
    except Exception as exc:
        logger.info("mcp_tool_error", tool="list_wiki_pages", error=str(exc))
        return MCPResponse.err(f"Failed to list wiki pages: {exc}").to_json()


@mcp.tool(
    description=(
        "Retrieves the full Markdown content of a single wiki page. "
        "Use when you need the exact content of a known page, "
        "or when query_wiki points to a specific page worth reading in full."
    )
)
async def get_wiki_page(workspace_id: str, page_path: str) -> str:
    logger.info("mcp_tool_call", tool="get_wiki_page", workspace_id=workspace_id)
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return MCPResponse.err(f"Invalid workspace_id: {workspace_id!r}").to_json()

    page_path = page_path.lstrip("/")

    try:
        async with AsyncSessionLocal() as db:
            from app.git.repo_manager import RepoManager
            from app.models.wiki_page import WikiPage

            result = await db.execute(
                select(WikiPage).where(
                    WikiPage.workspace_id == ws_uuid,
                    WikiPage.page_path == page_path,
                )
            )
            page = result.scalar_one_or_none()
            if not page:
                return MCPResponse.err(f"Page not found: {page_path}").to_json()

            repo = RepoManager(ws_uuid)
            content = repo.read_file(page_path) or ""

        return MCPResponse(
            summary=f"Retrieved page '{page.title}' ({len(content.split())} words).",
            data={
                "page_path": page.page_path,
                "title": page.title,
                "content": content,
                "updated_at": page.updated_at.isoformat() if page.updated_at else None,
            },
        ).to_json()
    except Exception as exc:
        logger.info("mcp_tool_error", tool="get_wiki_page", error=str(exc))
        return MCPResponse.err(f"Failed to get wiki page: {exc}").to_json()


@mcp.tool(
    description=(
        "Creates a new wiki page with provided Markdown content and commits it to git. "
        "Prefer update_wiki_page if the page already exists. "
        "page_path should be a relative path like 'concepts/new-topic.md'."
    )
)
async def create_wiki_page(workspace_id: str, page_path: str, title: str, content: str) -> str:
    logger.info("mcp_tool_call", tool="create_wiki_page", workspace_id=workspace_id)
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return MCPResponse.err(f"Invalid workspace_id: {workspace_id!r}").to_json()
    if not content.strip():
        return MCPResponse.err("content must not be empty.").to_json()

    page_path = page_path.lstrip("/")

    try:
        async with AsyncSessionLocal() as db:
            from app.git.repo_manager import RepoManager
            from app.models.wiki_page import WikiPage
            from app.services.embedding_service import get_embedding_service

            user = await get_mcp_service_user(db)
            repo = RepoManager(ws_uuid)
            sha = repo.write_file(page_path, content, f"mcp create: {page_path}")

            embed_svc = get_embedding_service()
            embedding = await embed_svc.embed_single(content)

            page = WikiPage(
                workspace_id=ws_uuid,
                page_path=page_path,
                title=title,
                page_type="manual",
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                git_commit_sha=sha,
                word_count=len(content.split()),
                embedding=embedding,
                original_embedding=embedding,
                created_by=user.id,
                updated_by=user.id,
            )
            db.add(page)
            await db.commit()

        return MCPResponse(
            summary=f"Created wiki page '{page_path}' (commit {sha[:8]}).",
            data={"page_path": page_path, "action": "created", "commit_sha": sha},
        ).to_json()
    except Exception as exc:
        logger.info("mcp_tool_error", tool="create_wiki_page", error=str(exc))
        return MCPResponse.err(f"Failed to create wiki page: {exc}").to_json()


@mcp.tool(
    description=(
        "Updates an existing wiki page with new Markdown content and commits to git. "
        "The full new content replaces the existing content. "
        "Use when you have new information that expands or corrects an existing page."
    )
)
async def update_wiki_page(workspace_id: str, page_path: str, content: str) -> str:
    logger.info("mcp_tool_call", tool="update_wiki_page", workspace_id=workspace_id)
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return MCPResponse.err(f"Invalid workspace_id: {workspace_id!r}").to_json()
    if not content.strip():
        return MCPResponse.err("content must not be empty.").to_json()

    page_path = page_path.lstrip("/")

    try:
        async with AsyncSessionLocal() as db:
            from app.git.repo_manager import RepoManager
            from app.models.wiki_page import WikiPage
            from app.services.embedding_service import get_embedding_service

            user = await get_mcp_service_user(db)
            result = await db.execute(
                select(WikiPage).where(
                    WikiPage.workspace_id == ws_uuid,
                    WikiPage.page_path == page_path,
                )
            )
            page = result.scalar_one_or_none()
            if not page:
                return MCPResponse.err(f"Page not found: {page_path}").to_json()

            repo = RepoManager(ws_uuid)
            sha = repo.write_file(page_path, content, f"mcp update: {page_path}")

            embed_svc = get_embedding_service()
            new_embedding = await embed_svc.embed_single(content)

            page.content_hash = hashlib.sha256(content.encode()).hexdigest()
            page.git_commit_sha = sha
            page.word_count = len(content.split())
            page.embedding = new_embedding
            page.updated_by = user.id
            await db.commit()

        return MCPResponse(
            summary=f"Updated wiki page '{page_path}' (commit {sha[:8]}).",
            data={"page_path": page_path, "action": "updated", "commit_sha": sha},
        ).to_json()
    except Exception as exc:
        logger.info("mcp_tool_error", tool="update_wiki_page", error=str(exc))
        return MCPResponse.err(f"Failed to update wiki page: {exc}").to_json()
