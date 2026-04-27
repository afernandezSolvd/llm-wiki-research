"""
Celery task: process an ingest job.

Flow:
  1. Load sources from DB
  2. Chunk + embed each source (via subtasks)
  3. Hybrid retrieval of relevant wiki context
  4. LLM ingest call → page edits + KG entities
  5. Apply page edits (git commit + DB update)
  6. Upsert KG nodes/edges
  7. Trigger community rebuild (debounced)
  8. Update IngestJob status
"""
import asyncio
import hashlib
import uuid
from datetime import UTC, datetime

from app.workers.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


def _run(coro):
    """Run an async coroutine from a sync Celery task."""
    return asyncio.run(coro)


@celery_app.task(name="app.workers.ingest_worker.process_ingest_job", bind=True, max_retries=3)
def process_ingest_job(self, job_id: str):
    """Main ingest task. All DB/LLM work happens inside the async helper."""
    try:
        _run(_process_ingest_job_async(uuid.UUID(job_id)))
    except Exception as exc:
        logger.error("ingest_job_failed", job_id=job_id, error=str(exc))
        _run(_mark_job_failed(uuid.UUID(job_id), str(exc)))
        raise self.retry(exc=exc, countdown=60)


async def _process_ingest_job_async(job_id: uuid.UUID):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.pool import NullPool
    import redis.asyncio as aioredis
    from app.config import get_settings
    from app.core.storage import get_storage
    from app.git.repo_manager import RepoManager
    from app.llm.client import get_anthropic_client, make_cached_block, make_text_block, extract_usage, estimate_cost_usd
    from app.llm.prompt_cache import get_schema_block, get_hot_pages_block, get_top_page_ids, mark_hot_pages_dirty
    from app.llm.prompts.ingest import INGEST_SYSTEM, INGEST_USER_TEMPLATE, INGEST_TOOLS
    from app.llm.prompts.verify import VERIFY_SYSTEM, VERIFY_USER_TEMPLATE
    from app.llm.output_parsers.wiki_diff import parse_ingest_tool_calls
    from app.models.ingest_job import IngestJob
    from app.models.source import Source, SourceChunk
    from app.models.wiki_page import WikiPage, WikiPageVersion, WikiPageSourceMap
    from app.models.schema_config import SchemaConfig
    from app.services.embedding_service import get_embedding_service
    from app.services.graph_service import upsert_node, upsert_edge
    from app.retrieval.vector_search import search_wiki_pages
    from app.retrieval.graph_traversal import find_seed_nodes, traverse_graph
    from app.retrieval.hybrid_ranker import rrf_fuse
    from sqlalchemy import select, update

    settings = get_settings()
    embed_svc = get_embedding_service()
    storage = get_storage()
    # NullPool: no persistent pool state across asyncio.run() calls in Celery workers
    _engine = create_async_engine(settings.database_url, poolclass=NullPool)
    _SessionLocal = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    redis = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    client = get_anthropic_client()

    async def _progress(stage: str) -> None:
        try:
            await redis.set(f"ingest:progress:{job_id}", stage, ex=86400)
        except Exception:
            pass

    async with _SessionLocal() as db:
        # Load job
        job = await db.get(IngestJob, job_id)
        if not job:
            logger.error("ingest_job_not_found", job_id=str(job_id))
            return

        job.status = "running"
        job.started_at = datetime.now(UTC).isoformat()
        await db.commit()

        workspace_id = job.workspace_id
        source_ids = job.source_ids or []

        # Load schema
        schema_result = await db.execute(
            select(SchemaConfig).where(SchemaConfig.workspace_id == workspace_id)
        )
        schema_cfg = schema_result.scalar_one_or_none()
        schema_content = schema_cfg.content if schema_cfg else "# Default Schema"

        # Load sources + chunk + embed
        pages_touched_ids: list[uuid.UUID] = []
        new_page_ids: list[uuid.UUID] = []  # pages created this job — drift anchor finalized on success
        total_usage = {"input_tokens": 0, "output_tokens": 0,
                       "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}

        for src_idx, source_id in enumerate(source_ids, 1):
            source = await db.get(Source, source_id)
            if not source:
                continue

            src_label = f"[{src_idx}/{len(source_ids)}] {source.title[:40]}"
            await _progress(f"loading {src_label}")
            source.ingest_status = "processing"
            await db.commit()

            # Load raw content
            try:
                raw_bytes = await storage.download(source.storage_key)
                raw_text = _extract_text(raw_bytes, source.source_type)
            except Exception as e:
                logger.error("source_download_failed", source_id=str(source_id), error=str(e))
                source.ingest_status = "failed"
                await db.commit()
                continue

            # Chunk + embed
            await _progress(f"chunking {src_label}")
            chunks = embed_svc.chunk_text(raw_text)
            await _progress(f"embedding {len(chunks)} chunks — {src_label}")
            embeddings = await embed_svc.embed_texts(chunks)

            # Clear existing chunks for idempotent re-ingestion
            from sqlalchemy import delete as sa_delete
            await db.execute(
                sa_delete(SourceChunk).where(SourceChunk.source_id == source_id)
            )
            await db.flush()

            now_str = datetime.now(UTC).isoformat()
            for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
                db.add(SourceChunk(
                    source_id=source_id,
                    workspace_id=workspace_id,
                    chunk_index=i,
                    chunk_text=chunk_text,
                    token_count=len(chunk_text.split()),
                    embedding=embedding,
                    created_at=now_str,
                ))
            await db.flush()

            # --- Build wiki context via hybrid retrieval ---
            await _progress(f"retrieving context — {src_label}")
            source_summary = raw_text[:8000]
            source_embedding = await embed_svc.embed_single(source_summary)

            vector_hits = await search_wiki_pages(db, workspace_id, source_embedding, top_k=15)

            # Extract rough entity names from source for graph traversal
            entity_names = _extract_proper_nouns(source_summary)
            seed_ids = await find_seed_nodes(db, workspace_id, entity_names)
            graph_hits = await traverse_graph(db, workspace_id, seed_ids, max_depth=2, top_k=10)

            fused_hits = rrf_fuse(vector_hits, graph_hits, top_k=20)

            # Load page contents for context
            wiki_context_parts = []
            for hit in fused_hits[:10]:
                if hit.page_id:
                    page = await db.get(WikiPage, hit.page_id)
                    if page:
                        repo = RepoManager(workspace_id)
                        content = repo.read_file(page.page_path) or ""
                        wiki_context_parts.append(f"### {page.title}\n{content[:2000]}")

            wiki_context = "\n\n".join(wiki_context_parts) or "_No existing wiki pages._"

            # Load hot pages for prompt caching
            top_page_ids = await get_top_page_ids(redis, workspace_id, settings.hot_pages_cache_top_n)
            hot_page_contents: list[tuple[str, str]] = []
            for pid in top_page_ids:
                page = await db.get(WikiPage, pid)
                if page:
                    repo = RepoManager(workspace_id)
                    content = repo.read_file(page.page_path) or ""
                    hot_page_contents.append((page.title, content[:1500]))

            # Build prompt with caching
            schema_block = await get_schema_block(redis, workspace_id, schema_content)
            system_blocks = [schema_block]
            if hot_page_contents:
                hot_block = await get_hot_pages_block(redis, workspace_id, hot_page_contents)
                system_blocks.append(hot_block)

            # Use Template substitution — safe against {} in source content
            user_text = (
                INGEST_USER_TEMPLATE
                .replace("${title}", source.title)
                .replace("${source_type}", source.source_type)
                .replace("${content}", source_summary)
                .replace("${wiki_context}", wiki_context)
            )

            await _progress(f"LLM generating — {src_label}")
            # LLM call
            response = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=8000,
                system=system_blocks,
                messages=[{"role": "user", "content": user_text}],
                tools=INGEST_TOOLS,
                tool_choice={"type": "auto"},
            )

            usage = extract_usage(response)
            for k in total_usage:
                total_usage[k] += usage[k]

            # Parse tool calls
            tool_calls = [
                {"name": b.name, "input": b.input}
                for b in response.content
                if b.type == "tool_use"
            ]
            ingest_result = parse_ingest_tool_calls(tool_calls)

            repo = RepoManager(workspace_id)

            # ── Hallucination gate ─────────────────────────────────────────────
            # Verify each proposed page edit against the source before committing.
            # Uses claude-haiku-4-5 (cheap + fast) to keep gate cost low.
            # Disable with HALLUCINATION_GATE_ENABLED=false for dev speed.
            verified_edits = []
            for edit in ingest_result.page_edits:
                if not settings.hallucination_gate_enabled:
                    verified_edits.append(edit)
                    continue

                # Gate is enabled — verify proposed edit against source before committing
                # Include title so title-derived attributions (e.g. "by Author") are valid
                source_with_title = f"Source title: {source.title}\n---\n{source_summary[:5900]}"
                verify_user = (
                    VERIFY_USER_TEMPLATE
                    .replace("${source_content}", source_with_title)
                    .replace("${page_title}", edit.title)
                    .replace("${page_content}", edit.content[:3000])
                )
                verify_resp = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=512,
                    system=VERIFY_SYSTEM,
                    messages=[{"role": "user", "content": verify_user}],
                )
                verify_text = next(
                    (b.text for b in verify_resp.content if b.type == "text"), "{}"
                )
                try:
                    import json as _json
                    verdict_data = _json.loads(
                        verify_text[verify_text.index("{"):verify_text.rindex("}") + 1]
                    )
                    verdict = verdict_data.get("verdict", "needs_review")
                    unsupported = verdict_data.get("unsupported_claims", [])
                except Exception:
                    verdict = "needs_review"
                    unsupported = []

                if verdict == "fail":
                    logger.warning(
                        "hallucination_gate_blocked",
                        page_path=edit.page_path,
                        unsupported_claims=unsupported[:3],
                    )
                    # Skip this edit — do NOT commit to git
                    continue

                if verdict == "needs_review":
                    # Append a review notice to the page content
                    edit = edit.__class__(
                        page_path=edit.page_path,
                        title=edit.title,
                        page_type=edit.page_type,
                        content=edit.content + "\n\n> **Note:** Some claims in this page could not be fully verified against the source and may require human review.",
                        change_summary=edit.change_summary,
                    )

                verified_edits.append(edit)

            await _progress(f"applying {len(verified_edits)} edits — {src_label}")
            # Apply page edits
            for edit in verified_edits:
                old_content = repo.read_file(edit.page_path) or ""
                commit_msg = f"ingest:{source_id} — {edit.change_summary[:80]}"
                sha = repo.write_file(edit.page_path, edit.content, commit_msg)

                if settings.wiki_git_enabled:
                    from app.workers.git_push_worker import push_to_remote as _git_push
                    _git_push.apply_async(args=[str(workspace_id)], queue="git_push")

                diff = repo.compute_diff(old_content, edit.content, edit.page_path)
                new_embedding = await embed_svc.embed_single(edit.content)

                content_hash = hashlib.sha256(edit.content.encode()).hexdigest()
                word_count = len(edit.content.split())

                # Upsert wiki_pages record
                existing_page = await db.execute(
                    select(WikiPage).where(
                        WikiPage.workspace_id == workspace_id,
                        WikiPage.page_path == edit.page_path,
                    )
                )
                page = existing_page.scalar_one_or_none()
                old_embedding: list[float] | None = None  # set in else-branch for drift calc
                if page is None:
                    page = WikiPage(
                        workspace_id=workspace_id,
                        page_path=edit.page_path,
                        title=edit.title,
                        page_type=edit.page_type,
                        content_hash=content_hash,
                        git_commit_sha=sha,
                        word_count=word_count,
                        embedding=new_embedding,
                        original_embedding=new_embedding,  # finalized at job success below
                        updated_by=job.triggered_by,
                        created_by=job.triggered_by,
                    )
                    db.add(page)
                    await db.flush()
                    new_page_ids.append(page.id)
                else:
                    # Capture old embedding BEFORE overwriting — used for drift score below
                    old_embedding = list(page.embedding) if page.embedding is not None else None
                    drift = _cosine_distance(old_embedding, new_embedding)
                    page.title = edit.title
                    page.page_type = edit.page_type
                    page.content_hash = content_hash
                    page.git_commit_sha = sha
                    page.word_count = word_count
                    page.embedding = new_embedding
                    page.updated_by = job.triggered_by

                    if drift and drift > settings.drift_alert_threshold:
                        logger.warning(
                            "high_semantic_drift",
                            page_path=edit.page_path,
                            drift=round(drift, 3),
                        )

                # Version record.
                # semantic_drift_score = distance from PREVIOUS version (incremental).
                # Absolute drift (from original) is computed in lint using original_embedding.
                now_str = datetime.now(UTC).isoformat()
                prev_embedding = old_embedding if old_content else None
                db.add(WikiPageVersion(
                    wiki_page_id=page.id,
                    workspace_id=workspace_id,
                    git_commit_sha=sha,
                    content=edit.content,
                    diff_from_prev=diff or None,
                    semantic_drift_score=_cosine_distance(prev_embedding, new_embedding),
                    change_reason=f"ingest:{source_id}",
                    changed_by=job.triggered_by,
                    created_at=now_str,
                ))

                # Provenance: upsert wiki_page_source_map
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                await db.execute(
                    pg_insert(WikiPageSourceMap)
                    .values(
                        wiki_page_id=page.id,
                        source_id=source_id,
                        workspace_id=workspace_id,
                        first_commit_sha=sha,
                        latest_commit_sha=sha,
                    )
                    .on_conflict_do_update(
                        index_elements=["wiki_page_id", "source_id"],
                        set_={"latest_commit_sha": sha, "updated_at": datetime.now(UTC)},
                    )
                )

                pages_touched_ids.append(page.id)
                await db.flush()

            await _progress(f"upserting KG — {src_label}")
            # Upsert KG entities + relations
            entity_name_to_id: dict[str, uuid.UUID] = {}
            for entity in ingest_result.kg_entities:
                node_id = await upsert_node(
                    db, workspace_id, entity.name, entity.entity_type,
                    entity.aliases, source_id
                )
                entity_name_to_id[entity.name] = node_id
                await db.flush()

            for rel in ingest_result.kg_relations:
                src_id = entity_name_to_id.get(rel.source)
                tgt_id = entity_name_to_id.get(rel.target)
                if src_id and tgt_id:
                    await upsert_edge(
                        db, workspace_id, src_id, tgt_id, rel.relation, rel.confidence,
                        evidence={"source_id": str(source_id)},
                    )

            source.ingest_status = "done"
            await db.commit()

        # Re-anchor original_embedding for all pages created this job now that
        # the job succeeded. If the job had failed and rolled back, no anchor
        # would have been locked in from partial/low-context LLM output.
        if new_page_ids:
            from sqlalchemy import update as sa_update
            await db.execute(
                sa_update(WikiPage)
                .where(WikiPage.id.in_(new_page_ids))
                .values(original_embedding=WikiPage.embedding)
            )
            await db.commit()
            await _progress(f"anchored {len(new_page_ids)} new page(s)")

        # Mark hot pages dirty if any touched pages are in hot set
        top_ids = set(str(i) for i in await get_top_page_ids(redis, workspace_id, settings.hot_pages_cache_top_n))
        if any(str(p) in top_ids for p in pages_touched_ids):
            await mark_hot_pages_dirty(redis, workspace_id)

        # Finalize job
        job.status = "done"
        job.pages_touched = pages_touched_ids
        job.completed_at = datetime.now(UTC).isoformat()
        job.llm_tokens_used = total_usage["input_tokens"] + total_usage["output_tokens"]
        job.llm_cost_usd = float(estimate_cost_usd(total_usage))
        await db.commit()

        # Trigger KG community rebuild (debounced via Redis)
        from app.workers.graph_worker import maybe_rebuild_communities
        maybe_rebuild_communities.apply_async(
            args=[str(workspace_id)], queue="graph", countdown=5
        )

        # Auto-trigger incremental lint pass for pages touched this job
        try:
            from app.models.lint_run import LintRun
            from app.workers.lint_worker import run_lint_pass
            lint_run = LintRun(
                workspace_id=workspace_id,
                scope="incremental",
                page_ids_scoped=pages_touched_ids,
            )
            db.add(lint_run)
            await db.commit()
            run_lint_pass.apply_async(args=[str(lint_run.id)], queue="lint")
            logger.info(
                "incremental_lint_triggered",
                lint_run_id=str(lint_run.id),
                pages_scoped=len(pages_touched_ids),
            )
        except Exception as lint_exc:
            logger.warning("incremental_lint_trigger_failed", error=str(lint_exc))

        logger.info(
            "ingest_job_completed",
            job_id=str(job_id),
            pages_touched=len(pages_touched_ids),
            tokens=job.llm_tokens_used,
            cost_usd=round(job.llm_cost_usd, 4),
        )

    await redis.aclose()
    await _engine.dispose()


async def _mark_job_failed(job_id: uuid.UUID, error: str):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.pool import NullPool
    from app.config import get_settings
    from app.models.ingest_job import IngestJob

    settings = get_settings()
    _engine = create_async_engine(settings.database_url, poolclass=NullPool)
    _SessionLocal = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

    async with _SessionLocal() as db:
        job = await db.get(IngestJob, job_id)
        if job:
            job.status = "failed"
            job.error_message = error[:1000]
            job.completed_at = datetime.now(UTC).isoformat()
            await db.commit()

    await _engine.dispose()


def _extract_text(raw_bytes: bytes, source_type: str) -> str:
    """Extract plain text from raw bytes based on source type."""
    if source_type == "pdf":
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=raw_bytes, filetype="pdf")
            pages_text = []
            for page in doc:
                pages_text.append(page.get_text())
            return "\n\n".join(pages_text)
        except Exception as e:
            logger.warning("pdf_extraction_failed_fallback_utf8", error=str(e))
            return raw_bytes.decode("utf-8", errors="replace")
    elif source_type == "url":
        # HTML — strip tags for plain-text extraction
        try:
            from html.parser import HTMLParser

            class _Strip(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self._parts: list[str] = []
                    self._skip = False

                def handle_starttag(self, tag, attrs):
                    self._skip = tag in ("script", "style")

                def handle_endtag(self, tag):
                    if tag in ("script", "style"):
                        self._skip = False

                def handle_data(self, data):
                    if not self._skip:
                        self._parts.append(data)

                def get_text(self):
                    return " ".join(self._parts)

            parser = _Strip()
            parser.feed(raw_bytes.decode("utf-8", errors="replace"))
            return parser.get_text()
        except Exception:
            return raw_bytes.decode("utf-8", errors="replace")
    elif source_type == "image":
        # Images need vision — return empty for now; handled by a future vision ingest pass
        return ""
    else:
        return raw_bytes.decode("utf-8", errors="replace")


def _extract_proper_nouns(text: str) -> list[str]:
    """Very rough heuristic: words that start with a capital letter."""
    import re
    words = re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", text)
    # Deduplicate and cap
    return list(dict.fromkeys(words))[:50]


def _cosine_distance(a: list[float] | None, b: list[float] | None) -> float | None:
    if a is None or b is None:
        return None
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return None
    cosine_sim = dot / (norm_a * norm_b)
    return 1.0 - cosine_sim  # distance
