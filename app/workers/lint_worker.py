"""
Celery task: run a lint pass over wiki pages.

Phases:
  1. Structural checks (orphans, missing xrefs, stale claims) — no LLM
  2. Semantic drift monitoring — no LLM
  3. Contradiction detection — LLM in batches
  4. Optional auto-fix
"""
import asyncio
import uuid
from datetime import UTC, datetime

from app.workers.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


def _run(coro):
    return asyncio.run(coro)


@celery_app.task(name="app.workers.lint_worker.run_lint_pass", bind=True, max_retries=2)
def run_lint_pass(self, run_id: str):
    try:
        _run(_run_lint_pass_async(uuid.UUID(run_id)))
    except Exception as exc:
        logger.error("lint_run_failed", run_id=run_id, error=str(exc))
        _run(_mark_run_failed(uuid.UUID(run_id), str(exc)))
        raise self.retry(exc=exc, countdown=120)


async def _run_lint_pass_async(run_id: uuid.UUID):
    from app.core.db import AsyncSessionLocal
    from app.core.redis import get_redis_pool
    from app.config import get_settings
    from app.git.repo_manager import RepoManager
    from app.llm.client import get_anthropic_client, make_cached_block
    from app.llm.prompt_cache import get_schema_block
    from app.llm.prompts.lint import LINT_SYSTEM, LINT_USER_TEMPLATE
    from app.llm.output_parsers.lint_findings import parse_lint_response
    from app.models.lint_run import LintRun, LintFinding
    from app.models.wiki_page import WikiPage, WikiPageVersion
    from app.models.schema_config import SchemaConfig
    from app.models.knowledge_graph import KGEdge, KGNode
    from sqlalchemy import select, func

    settings = get_settings()
    client = get_anthropic_client()
    redis = get_redis_pool()
    now_str = datetime.now(UTC).isoformat()

    async with AsyncSessionLocal() as db:
        run = await db.get(LintRun, run_id)
        if not run:
            return

        run.status = "running"
        await db.commit()

        workspace_id = run.workspace_id

        # Load pages to lint
        if run.page_ids_scoped:
            pages_result = await db.execute(
                select(WikiPage).where(
                    WikiPage.workspace_id == workspace_id,
                    WikiPage.id.in_(run.page_ids_scoped),
                )
            )
        else:
            pages_result = await db.execute(
                select(WikiPage).where(WikiPage.workspace_id == workspace_id)
            )
        pages = pages_result.scalars().all()

        findings: list[LintFinding] = []
        repo = RepoManager(workspace_id)

        # ── Phase 1: Structural checks ─────────────────────────────────────────
        # Build wikilink index once — O(N) reads total, O(1) per-page lookup.
        # Maps page_path → set of page_paths that link TO it.
        from app.git.diff_parser import extract_wikilinks
        inbound_links: dict[str, set[str]] = {p.page_path: set() for p in pages}
        for p in pages:
            content = repo.read_file(p.page_path) or ""
            for target in extract_wikilinks(content):
                if target in inbound_links:
                    inbound_links[target].add(p.page_path)
            # Also scan for bare path references like (pages/entities/openai.md)
            import re
            for match in re.finditer(r"\(?(pages/[^\s\)\"]+\.md)\)?", content):
                target = match.group(1)
                if target in inbound_links:
                    inbound_links[target].add(p.page_path)

        for page in pages:
            # KG inbound edge count
            inbound = await db.execute(
                select(func.count(KGEdge.id)).where(
                    KGEdge.workspace_id == workspace_id,
                    KGEdge.target_node_id.in_(
                        select(KGNode.id).where(
                            KGNode.workspace_id == workspace_id,
                            KGNode.wiki_page_id == page.id,
                        )
                    ),
                )
            )
            inbound_count = inbound.scalar() or 0
            has_inbound_link = bool(inbound_links.get(page.page_path))

            if inbound_count == 0 and not has_inbound_link and page.page_type not in ("index", "log"):
                findings.append(LintFinding(
                    lint_run_id=run_id,
                    workspace_id=workspace_id,
                    wiki_page_id=page.id,
                    finding_type="orphan",
                    severity="warning",
                    description=f"Page '{page.page_path}' has no inbound links or KG edges.",
                    created_at=now_str,
                ))

        # ── Phase 2: Origin-anchored semantic drift ────────────────────────────
        # Absolute drift = cosine_distance(original_embedding, current_embedding).
        # One number, no accumulation artifacts — flags pages that have moved far
        # from what they were when first written.
        from app.workers.ingest_worker import _cosine_distance
        for page in pages:
            if page.original_embedding is None or page.embedding is None:
                continue

            abs_drift = _cosine_distance(
                list(page.original_embedding), list(page.embedding)
            )
            if abs_drift is None:
                continue

            version_count_result = await db.execute(
                select(func.count(WikiPageVersion.id)).where(
                    WikiPageVersion.wiki_page_id == page.id
                )
            )
            version_count = version_count_result.scalar() or 0

            if abs_drift > settings.drift_alert_threshold:
                findings.append(LintFinding(
                    lint_run_id=run_id,
                    workspace_id=workspace_id,
                    wiki_page_id=page.id,
                    finding_type="semantic_drift",
                    severity="error" if abs_drift > settings.drift_alert_threshold * 2 else "warning",
                    description=(
                        f"Page '{page.page_path}' has drifted {abs_drift:.3f} from its original "
                        f"meaning across {version_count} versions (threshold: {settings.drift_alert_threshold})."
                    ),
                    evidence={
                        "absolute_drift": round(abs_drift, 4),
                        "threshold": settings.drift_alert_threshold,
                        "version_count": version_count,
                    },
                    created_at=now_str,
                ))

        # ── Phase 3: LLM contradiction detection ──────────────────────────────
        schema_result = await db.execute(
            select(SchemaConfig).where(SchemaConfig.workspace_id == workspace_id)
        )
        schema_cfg = schema_result.scalar_one_or_none()
        schema_content = schema_cfg.content if schema_cfg else ""

        schema_block = await get_schema_block(redis, workspace_id, schema_content)

        # Build candidate pairs: pages in the same KG community
        page_pairs: list[tuple[WikiPage, WikiPage, str]] = []  # (a, b, pair_source)
        community_to_pages: dict[str, list[WikiPage]] = {}
        pages_with_kg: set[uuid.UUID] = set()
        for page in pages:
            node_result = await db.execute(
                select(KGNode).where(
                    KGNode.workspace_id == workspace_id,
                    KGNode.wiki_page_id == page.id,
                )
            )
            node = node_result.scalar_one_or_none()
            if node and node.community_id:
                cid = str(node.community_id)
                community_to_pages.setdefault(cid, []).append(page)
                pages_with_kg.add(page.id)

        for community_pages in community_to_pages.values():
            for i in range(len(community_pages)):
                for j in range(i + 1, min(i + 4, len(community_pages))):  # cap pairs per community
                    page_pairs.append((community_pages[i], community_pages[j], "kg_community"))

        # Embedding-similarity pairs for pages outside KG communities
        kg_pairs_count = len(page_pairs)
        covered_pairs: set[frozenset[uuid.UUID]] = {
            frozenset({a.id, b.id}) for a, b, _ in page_pairs
        }
        embedding_pairs_count = 0
        from sqlalchemy import text as sa_text
        for page in pages:
            if page.id in pages_with_kg or page.embedding is None:
                continue
            if embedding_pairs_count >= 30:
                break
            vec_str = "[" + ",".join(str(x) for x in page.embedding) + "]"
            neighbors_result = await db.execute(
                sa_text(
                    "SELECT id FROM wiki_pages "
                    "WHERE workspace_id = :ws AND id != :pid AND embedding IS NOT NULL "
                    "ORDER BY embedding <=> cast(:ref_embedding as vector) LIMIT 3"
                ),
                {"ws": workspace_id, "pid": page.id, "ref_embedding": vec_str},
            )
            for (neighbor_id,) in neighbors_result:
                pair_key = frozenset({page.id, neighbor_id})
                if pair_key in covered_pairs:
                    continue
                neighbor_page = await db.get(WikiPage, neighbor_id)
                if neighbor_page and embedding_pairs_count < 30:
                    page_pairs.append((page, neighbor_page, "embedding_similarity"))
                    covered_pairs.add(pair_key)
                    embedding_pairs_count += 1

        logger.info(
            "lint_phase3_pairs_built",
            community_pairs=kg_pairs_count,
            embedding_pairs=embedding_pairs_count,
            total_pairs=len(page_pairs),
        )

        # Prioritize KG community pairs first (up to 70), then embedding pairs (up to 30)
        kg_slice = [p for p in page_pairs if p[2] == "kg_community"][:70]
        emb_slice = [p for p in page_pairs if p[2] == "embedding_similarity"][:30]
        pairs_to_check = kg_slice + emb_slice

        for page_a, page_b, pair_source in pairs_to_check[:100]:  # cap total LLM calls
            content_a = repo.read_file(page_a.page_path) or ""
            content_b = repo.read_file(page_b.page_path) or ""
            if not content_a or not content_b:
                continue

            user_text = (
                LINT_USER_TEMPLATE
                .replace("${path_a}", page_a.page_path)
                .replace("${title_a}", page_a.title)
                .replace("${content_a}", content_a[:3000])
                .replace("${path_b}", page_b.page_path)
                .replace("${title_b}", page_b.title)
                .replace("${content_b}", content_b[:3000])
            )

            response = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=1000,
                system=[schema_block, {"type": "text", "text": LINT_SYSTEM}],
                messages=[{"role": "user", "content": user_text}],
            )

            text_content = next(
                (b.text for b in response.content if b.type == "text"), ""
            )
            llm_findings = parse_lint_response(text_content)

            for f in llm_findings:
                findings.append(LintFinding(
                    lint_run_id=run_id,
                    workspace_id=workspace_id,
                    wiki_page_id=page_a.id,
                    finding_type=f.finding_type,
                    severity=f.severity,
                    description=f.description,
                    evidence={
                        "conflicting_pages": [
                            {"path": page_a.page_path, "excerpt": f.page_a_excerpt},
                            {"path": page_b.page_path, "excerpt": f.page_b_excerpt},
                        ],
                        "topic": f.topic,
                        "pair_source": pair_source,
                        # backward compat keys
                        "page_a": page_a.page_path,
                        "page_b": page_b.page_path,
                        "page_a_excerpt": f.page_a_excerpt,
                        "page_b_excerpt": f.page_b_excerpt,
                    },
                    created_at=now_str,
                ))

        # Persist findings
        for finding in findings:
            db.add(finding)
        await db.flush()

        run.status = "done"
        run.finding_count = len(findings)
        run.completed_at = now_str
        await db.commit()

        logger.info(
            "lint_run_completed",
            run_id=str(run_id),
            findings=len(findings),
        )


async def _mark_run_failed(run_id: uuid.UUID, error: str):
    from app.core.db import AsyncSessionLocal
    from app.models.lint_run import LintRun

    async with AsyncSessionLocal() as db:
        run = await db.get(LintRun, run_id)
        if run:
            run.status = "failed"
            run.completed_at = datetime.now(UTC).isoformat()
            await db.commit()
