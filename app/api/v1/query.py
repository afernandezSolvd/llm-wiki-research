import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import Role, require_role
from app.config import get_settings
from app.core.db import get_db
from app.core.redis import get_redis_pool
from app.dependencies import get_current_user
from app.llm.client import estimate_cost_usd, extract_usage, get_anthropic_client
from app.llm.output_parsers.query_response import parse_query_response
from app.llm.prompt_cache import (
    get_hot_pages_block,
    get_schema_block,
    get_top_page_ids,
    increment_page_query_count,
)
from app.llm.prompts.query import QUERY_SYSTEM, QUERY_USER_TEMPLATE
from app.models.schema_config import SchemaConfig
from app.models.user import User
from app.models.wiki_page import WikiPage
from app.retrieval.graph_traversal import find_seed_nodes, traverse_graph
from app.retrieval.hybrid_ranker import rrf_fuse
from app.retrieval.vector_search import search_source_chunks, search_wiki_pages
from app.services.embedding_service import get_embedding_service
from app.git.repo_manager import RepoManager
from app.workers.ingest_worker import _extract_proper_nouns

router = APIRouter(prefix="/workspaces/{workspace_id}/query", tags=["query"])

settings = get_settings()


class QueryRequest(BaseModel):
    question: str
    top_k: int = 20
    save_as_exploration: bool = False
    # Persona context — shapes how the LLM frames its answer (@vishalmysore 5W1H)
    user_context: str | None = None


class QueryResponse(BaseModel):
    answer: str
    citations: list[dict]
    tokens_used: int
    cost_usd: float


async def _build_retrieval_context(
    db,
    workspace_id: uuid.UUID,
    question: str,
    query_embedding: list[float],
    top_k: int,
    redis,
) -> tuple[str, list]:
    """
    Hybrid retrieval: wiki pages (primary) + source chunks (fallback).
    Returns (context_str, hit_list).
    """
    # Wiki page hits
    wiki_hits = await search_wiki_pages(db, workspace_id, query_embedding, top_k=15)

    # KG graph hits
    entity_names = _extract_proper_nouns(question)
    seed_ids = await find_seed_nodes(db, workspace_id, entity_names)
    graph_hits = await traverse_graph(db, workspace_id, seed_ids, max_depth=2, top_k=10)

    # Source chunk hits — serve as fallback when wiki coverage is thin
    chunk_hits = await search_source_chunks(db, workspace_id, query_embedding, top_k=10)

    # Fuse all three. Wiki + graph first (preferred), chunks fill the gap.
    fused_wiki = rrf_fuse(wiki_hits, graph_hits, top_k=top_k)
    # Only include chunk hits if wiki coverage is thin
    if len(fused_wiki) < 5:
        fused_hits = rrf_fuse(fused_wiki, chunk_hits, top_k=top_k)
    else:
        fused_hits = fused_wiki + [h for h in chunk_hits if h.page_id is None][:5]

    # Track hot pages
    for hit in fused_hits:
        if hit.page_id:
            await increment_page_query_count(redis, workspace_id, hit.page_id)

    # Load content text
    repo = RepoManager(workspace_id)
    context_parts = []
    for hit in fused_hits[:15]:
        if hit.page_id:
            page = await db.get(WikiPage, hit.page_id)
            if page:
                content = repo.read_file(page.page_path) or ""
                context_parts.append(f"**[{page.title}]({page.page_path})**\n{content[:2000]}")
        elif hit.excerpt:
            context_parts.append(f"**[Source: {hit.title}]**\n{hit.excerpt}")

    context = "\n\n---\n\n".join(context_parts) or "_No relevant context found in the wiki._"
    return context, fused_hits


def _build_system_prompt(
    schema_block: dict,
    hot_block: dict | None,
    user_context: str | None,
) -> list[dict]:
    """Build system block list with optional persona framing."""
    # Cached blocks must come first (most stable → least stable)
    blocks: list[dict] = [schema_block]
    if hot_block:
        blocks.append(hot_block)
    # Non-cached: base system prompt + optional persona
    system_text = QUERY_SYSTEM
    if user_context:
        system_text += (
            f"\n\nContext about the person asking: {user_context}\n"
            "Tailor your answer's depth, terminology, and emphasis accordingly."
        )
    blocks.append({"type": "text", "text": system_text})
    return blocks


@router.post("", response_model=QueryResponse)
async def query(
    workspace_id: uuid.UUID,
    body: QueryRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)

    embed_svc = get_embedding_service()
    redis = get_redis_pool()
    client = get_anthropic_client()

    query_embedding = await embed_svc.embed_single(body.question)
    context, fused_hits = await _build_retrieval_context(
        db, workspace_id, body.question, query_embedding, body.top_k, redis
    )

    schema_result = await db.execute(
        select(SchemaConfig).where(SchemaConfig.workspace_id == workspace_id)
    )
    schema_cfg = schema_result.scalar_one_or_none()
    schema_content = schema_cfg.content if schema_cfg else ""

    schema_block = await get_schema_block(redis, workspace_id, schema_content)
    top_page_ids = await get_top_page_ids(redis, workspace_id, settings.hot_pages_cache_top_n)
    repo = RepoManager(workspace_id)
    hot_pages: list[tuple[str, str]] = []
    for pid in top_page_ids:
        page = await db.get(WikiPage, pid)
        if page:
            content = repo.read_file(page.page_path) or ""
            hot_pages.append((page.title, content[:1500]))

    hot_block = await get_hot_pages_block(redis, workspace_id, hot_pages) if hot_pages else None
    system_blocks = _build_system_prompt(schema_block, hot_block, body.user_context)

    # Safe template substitution (source may contain {})
    user_text = (
        QUERY_USER_TEMPLATE
        .replace("${question}", body.question)
        .replace("${context}", context)
    )

    # SSE streaming — if client sends Accept: text/event-stream
    accept = request.headers.get("accept", "")
    if "text/event-stream" in accept:
        return StreamingResponse(
            _stream_query(client, system_blocks, user_text, workspace_id, body, repo, db),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Standard synchronous response
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=4000,
        system=system_blocks,
        messages=[{"role": "user", "content": user_text}],
    )

    answer_text = next((b.text for b in response.content if b.type == "text"), "")
    usage = extract_usage(response)
    parsed = parse_query_response(answer_text)

    if body.save_as_exploration:
        import hashlib
        slug = hashlib.md5(body.question.encode()).hexdigest()[:8]
        page_path = f"pages/explorations/{slug}.md"
        repo.write_file(page_path, f"# Q: {body.question}\n\n{answer_text}", f"exploration: {body.question[:60]}")

    return QueryResponse(
        answer=parsed.answer_text,
        citations=[
            {"title": c.title, "page_path": c.page_path, "source_title": c.source_title}
            for c in parsed.citations
        ],
        tokens_used=usage["input_tokens"] + usage["output_tokens"],
        cost_usd=round(estimate_cost_usd(usage), 6),
    )


async def _stream_query(
    client,
    system_blocks: list[dict],
    user_text: str,
    workspace_id: uuid.UUID,
    body: QueryRequest,
    repo: RepoManager,
    db,
) -> AsyncGenerator[str, None]:
    """SSE stream: yields `data: {...}\n\n` events per text delta."""
    full_text = []

    with client.messages.stream(
        model=settings.anthropic_model,
        max_tokens=4000,
        system=system_blocks,
        messages=[{"role": "user", "content": user_text}],
    ) as stream:
        for text_delta in stream.text_stream:
            full_text.append(text_delta)
            yield f"data: {json.dumps({'delta': text_delta})}\n\n"

    answer = "".join(full_text)
    parsed = parse_query_response(answer)

    if body.save_as_exploration:
        import hashlib
        slug = hashlib.md5(body.question.encode()).hexdigest()[:8]
        repo.write_file(
            f"pages/explorations/{slug}.md",
            f"# Q: {body.question}\n\n{answer}",
            f"exploration: {body.question[:60]}",
        )

    # Final event with citations
    yield f"data: {json.dumps({'done': True, 'citations': [{'title': c.title, 'page_path': c.page_path} for c in parsed.citations]})}\n\n"
