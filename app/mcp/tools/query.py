import uuid

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.mcp.response import MCPResponse
from app.mcp.server import mcp

logger = get_logger(__name__)


@mcp.tool(
    description=(
        "Asks a natural-language question against the wiki and returns "
        "a synthesized answer with citations. "
        "Uses hybrid retrieval (semantic search + knowledge graph). "
        "Prefer this over reading individual wiki pages directly."
    )
)
async def query_wiki(
    workspace_id: str,
    question: str,
    top_k: int = 20,
    user_context: str = "",
) -> str:
    logger.info("mcp_tool_call", tool="query_wiki", workspace_id=workspace_id)
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return MCPResponse.err(f"Invalid workspace_id: {workspace_id!r}").to_json()
    if not question.strip():
        return MCPResponse.err("question must not be empty.").to_json()

    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            from app.api.v1.query import _build_retrieval_context, _build_system_prompt
            from app.config import get_settings
            from app.core.redis import get_redis_pool
            from app.git.repo_manager import RepoManager
            from app.llm.client import estimate_cost_usd, extract_usage, get_anthropic_client
            from app.llm.output_parsers.query_response import parse_query_response
            from app.llm.prompt_cache import get_hot_pages_block, get_schema_block, get_top_page_ids
            from app.llm.prompts.query import QUERY_USER_TEMPLATE
            from app.models.schema_config import SchemaConfig
            from app.models.wiki_page import WikiPage
            from app.services.embedding_service import get_embedding_service

            settings = get_settings()
            embed_svc = get_embedding_service()
            redis = get_redis_pool()
            client = get_anthropic_client()

            query_embedding = await embed_svc.embed_single(question)
            context, _ = await _build_retrieval_context(
                db, ws_uuid, question, query_embedding, top_k, redis
            )

            schema_result = await db.execute(
                select(SchemaConfig).where(SchemaConfig.workspace_id == ws_uuid)
            )
            schema_cfg = schema_result.scalar_one_or_none()
            schema_content = schema_cfg.content if schema_cfg else ""
            schema_block = await get_schema_block(redis, ws_uuid, schema_content)

            top_page_ids = await get_top_page_ids(redis, ws_uuid, settings.hot_pages_cache_top_n)
            repo = RepoManager(ws_uuid)
            hot_pages: list[tuple[str, str]] = []
            for pid in top_page_ids:
                page = await db.get(WikiPage, pid)
                if page:
                    content = repo.read_file(page.page_path) or ""
                    hot_pages.append((page.title, content[:1500]))

            hot_block = await get_hot_pages_block(redis, ws_uuid, hot_pages) if hot_pages else None
            system_blocks = _build_system_prompt(schema_block, hot_block, user_context or None)

            user_text = (
                QUERY_USER_TEMPLATE
                .replace("${question}", question)
                .replace("${context}", context)
            )

            response = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=4000,
                system=system_blocks,
                messages=[{"role": "user", "content": user_text}],
            )

        answer_text = next((b.text for b in response.content if b.type == "text"), "")
        usage = extract_usage(response)
        parsed = parse_query_response(answer_text)
        citations = [
            {"title": c.title, "page_path": c.page_path}
            for c in parsed.citations
        ]

        return MCPResponse(
            summary=(
                f"Answer retrieved with {len(citations)} citation(s). "
                f"Cost: ${round(estimate_cost_usd(usage), 4)}."
            ),
            data={
                "answer": parsed.answer_text,
                "citations": citations,
                "tokens_used": usage["input_tokens"] + usage["output_tokens"],
                "cost_usd": round(estimate_cost_usd(usage), 6),
            },
        ).to_json()
    except Exception as exc:
        logger.info("mcp_tool_error", tool="query_wiki", error=str(exc))
        return MCPResponse.err(f"Failed to query wiki: {exc}").to_json()
