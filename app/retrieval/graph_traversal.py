"""BFS graph traversal over kg_nodes/kg_edges using a recursive CTE."""
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval.vector_search import SearchHit


async def find_seed_nodes(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    entity_names: list[str],
) -> list[uuid.UUID]:
    """Find KG node IDs matching entity names (case-insensitive)."""
    if not entity_names:
        return []
    result = await db.execute(
        text(
            """
            SELECT id FROM kg_nodes
            WHERE workspace_id = :workspace_id
              AND (
                lower(entity_name) = ANY(:names)
                OR aliases && :names_arr
              )
            LIMIT 50
            """
        ),
        {
            "workspace_id": workspace_id,
            "names": [n.lower() for n in entity_names],
            "names_arr": entity_names,
        },
    )
    return [row.id for row in result.fetchall()]


async def traverse_graph(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    seed_node_ids: list[uuid.UUID],
    max_depth: int = 2,
    min_weight: float = 0.5,
    top_k: int = 10,
) -> list[SearchHit]:
    """
    BFS from seed nodes up to max_depth hops.
    Returns wiki pages reachable via the KG, ranked by hop distance + edge weight.
    """
    if not seed_node_ids:
        return []

    result = await db.execute(
        text(
            """
            WITH RECURSIVE subgraph AS (
                SELECT
                    n.id,
                    n.wiki_page_id,
                    0 AS depth,
                    1.0 AS cumulative_weight
                FROM kg_nodes n
                WHERE n.workspace_id = :workspace_id
                  AND n.id = ANY(:seed_ids)

                UNION

                SELECT
                    n2.id,
                    n2.wiki_page_id,
                    s.depth + 1,
                    s.cumulative_weight * e.weight
                FROM subgraph s
                JOIN kg_edges e ON e.source_node_id = s.id
                               AND e.workspace_id = :workspace_id
                               AND e.weight >= :min_weight
                JOIN kg_nodes n2 ON n2.id = e.target_node_id
                WHERE s.depth < :max_depth
            )
            SELECT DISTINCT ON (wp.id)
                wp.id AS page_id,
                wp.page_path,
                wp.title,
                MIN(sg.depth)    AS min_depth,
                MAX(sg.cumulative_weight) AS best_weight
            FROM subgraph sg
            JOIN wiki_pages wp ON wp.id = sg.wiki_page_id
            WHERE wp.workspace_id = :workspace_id
            GROUP BY wp.id, wp.page_path, wp.title
            ORDER BY wp.id, min_depth ASC, best_weight DESC
            LIMIT :top_k
            """
        ),
        {
            "workspace_id": workspace_id,
            "seed_ids": seed_node_ids,
            "min_weight": min_weight,
            "max_depth": max_depth,
            "top_k": top_k,
        },
    )
    rows = result.fetchall()
    return [
        SearchHit(
            page_id=row.page_id,
            chunk_id=None,
            page_path=row.page_path,
            title=row.title,
            excerpt="",
            # Score: closer hops and higher weight = better (normalize to 0-1)
            score=float(row.best_weight) / (1 + float(row.min_depth)),
            source="graph",
        )
        for row in rows
    ]
