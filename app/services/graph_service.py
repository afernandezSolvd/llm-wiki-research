"""Knowledge graph service: node/edge upsert, community detection."""
import uuid
from datetime import UTC, datetime

import networkx as nx
from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.knowledge_graph import KGCommunity, KGEdge, KGNode
from app.services.embedding_service import get_embedding_service

logger = get_logger(__name__)


async def upsert_node(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    entity_name: str,
    entity_type: str,
    aliases: list[str] | None = None,
    source_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert or update a KG node. Returns its ID."""
    stmt = (
        insert(KGNode)
        .values(
            workspace_id=workspace_id,
            entity_name=entity_name,
            entity_type=entity_type,
            aliases=aliases or [],
            source_ids=[source_id] if source_id else [],
        )
        .on_conflict_do_update(
            index_elements=["workspace_id", "entity_name", "entity_type"],
            set_={
                "aliases": text(
                    "ARRAY(SELECT DISTINCT unnest(kg_nodes.aliases || EXCLUDED.aliases))"
                ),
                "source_ids": text(
                    "ARRAY(SELECT DISTINCT unnest(kg_nodes.source_ids || EXCLUDED.source_ids))"
                ),
                "updated_at": datetime.now(UTC),
            },
        )
        .returning(KGNode.id)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def upsert_edge(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    source_node_id: uuid.UUID,
    target_node_id: uuid.UUID,
    relation_type: str,
    confidence: float = 1.0,
    evidence: dict | None = None,
) -> None:
    """Insert edge or increment its weight if it already exists."""
    existing = await db.execute(
        select(KGEdge).where(
            KGEdge.workspace_id == workspace_id,
            KGEdge.source_node_id == source_node_id,
            KGEdge.target_node_id == target_node_id,
            KGEdge.relation_type == relation_type,
        )
    )
    edge = existing.scalar_one_or_none()
    if edge:
        edge.weight = min(edge.weight + confidence, 10.0)  # cap at 10
        if evidence:
            existing_ev = edge.evidence or {"occurrences": []}
            existing_ev.setdefault("occurrences", []).append(evidence)
            edge.evidence = existing_ev
    else:
        db.add(
            KGEdge(
                workspace_id=workspace_id,
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                relation_type=relation_type,
                weight=confidence,
                evidence={"occurrences": [evidence]} if evidence else None,
            )
        )


# Hard cap: load at most this many edges into networkx.
# Above this, we sample by weight to keep memory bounded.
# At avg 200 bytes/edge in networkx, 500k edges ≈ 100 MB — safe for a worker.
MAX_EDGES_FOR_COMMUNITY_DETECTION = 500_000


async def rebuild_communities(db: AsyncSession, workspace_id: uuid.UUID) -> int:
    """
    Run Louvain community detection on the KG for this workspace.
    Returns number of communities found.

    For workspaces with > MAX_EDGES edges: loads only the top-weight edges so
    the networkx graph stays within memory bounds.
    """
    from sqlalchemy import func as sqlfunc

    # Count total edges first — avoid loading millions just to discover we need to sample
    count_result = await db.execute(
        select(sqlfunc.count(KGEdge.id)).where(KGEdge.workspace_id == workspace_id)
    )
    total_edges = count_result.scalar() or 0

    if total_edges < 3:
        logger.info("kg_community_rebuild_skipped_too_few_edges", workspace_id=str(workspace_id))
        return 0

    # Load edges, sampling by weight if total exceeds the cap
    edge_query = (
        select(KGEdge.source_node_id, KGEdge.target_node_id, KGEdge.weight)
        .where(KGEdge.workspace_id == workspace_id)
        .order_by(KGEdge.weight.desc())
        .limit(MAX_EDGES_FOR_COMMUNITY_DETECTION)
    )
    if total_edges > MAX_EDGES_FOR_COMMUNITY_DETECTION:
        logger.warning(
            "kg_community_rebuild_sampling_edges",
            workspace_id=str(workspace_id),
            total=total_edges,
            loaded=MAX_EDGES_FOR_COMMUNITY_DETECTION,
        )

    result = await db.execute(edge_query)
    edges = result.fetchall()

    if len(edges) < 3:
        return 0

    # Build networkx graph
    G = nx.Graph()
    for e in edges:
        G.add_edge(str(e.source_node_id), str(e.target_node_id), weight=e.weight)

    communities = nx.community.louvain_communities(G, seed=42)

    # Clear old communities for this workspace
    await db.execute(delete(KGCommunity).where(KGCommunity.workspace_id == workspace_id))
    await db.flush()

    embed_svc = get_embedding_service()

    for i, community_nodes in enumerate(communities):
        # Load entity names for labeling
        node_ids = [uuid.UUID(nid) for nid in community_nodes]
        names_result = await db.execute(
            select(KGNode.entity_name).where(
                KGNode.id.in_(node_ids[:20])  # sample for label generation
            )
        )
        names = [r.entity_name for r in names_result.fetchall()]
        label = ", ".join(names[:5]) + (f" (+{len(names)-5} more)" if len(names) > 5 else "")

        community_text = f"Community of {len(community_nodes)} entities: {', '.join(names[:30])}"
        embedding = await embed_svc.embed_single(community_text)

        community = KGCommunity(
            workspace_id=workspace_id,
            label=label,
            member_count=len(community_nodes),
            summary=community_text,
            embedding=embedding,
        )
        db.add(community)
        await db.flush()

        # Assign community to nodes
        await db.execute(
            update(KGNode)
            .where(KGNode.id.in_(node_ids))
            .values(community_id=community.id)
        )

    await db.commit()
    logger.info("kg_communities_rebuilt", workspace_id=str(workspace_id), count=len(communities))
    return len(communities)
