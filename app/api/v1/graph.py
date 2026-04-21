import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import Role, require_role
from app.core.db import get_db
from app.dependencies import get_current_user
from app.models.knowledge_graph import KGCommunity, KGEdge, KGNode
from app.models.user import User
from app.retrieval.graph_traversal import traverse_graph
from app.retrieval.vector_search import SearchHit
from app.services.embedding_service import get_embedding_service

router = APIRouter(prefix="/workspaces/{workspace_id}/graph", tags=["graph"])


class NodeResponse(BaseModel):
    id: uuid.UUID
    entity_name: str
    entity_type: str
    aliases: list[str] | None
    wiki_page_id: uuid.UUID | None
    community_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class CommunityResponse(BaseModel):
    id: uuid.UUID
    label: str
    member_count: int | None
    summary: str | None

    model_config = {"from_attributes": True}


class GraphSearchRequest(BaseModel):
    query: str
    top_k: int = 10


@router.get("/nodes", response_model=list[NodeResponse])
async def list_nodes(
    workspace_id: uuid.UUID,
    entity_type: str | None = None,
    community_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)
    q = (
        select(KGNode)
        .where(KGNode.workspace_id == workspace_id)
        .order_by(KGNode.entity_name)
        .limit(min(limit, 500))
        .offset(offset)
    )
    if entity_type:
        q = q.where(KGNode.entity_type == entity_type)
    if community_id:
        q = q.where(KGNode.community_id == community_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/nodes/{node_id}/neighbors")
async def get_neighbors(
    workspace_id: uuid.UUID,
    node_id: uuid.UUID,
    depth: int = 1,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)
    hits = await traverse_graph(db, workspace_id, [node_id], max_depth=depth, top_k=50)
    return [
        {"page_id": str(h.page_id), "page_path": h.page_path, "title": h.title, "score": h.score}
        for h in hits
    ]


@router.get("/communities", response_model=list[CommunityResponse])
async def list_communities(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)
    result = await db.execute(
        select(KGCommunity).where(KGCommunity.workspace_id == workspace_id)
    )
    return result.scalars().all()


@router.post("/search")
async def search_graph(
    workspace_id: uuid.UUID,
    body: GraphSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_role(db, current_user, workspace_id, Role.reader)

    embed_svc = get_embedding_service()
    query_embedding = await embed_svc.embed_single(body.query)

    vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    from sqlalchemy import text
    result = await db.execute(
        text(
            """
            SELECT id, entity_name, entity_type,
                   1 - (embedding <=> :embedding::vector) AS score
            FROM kg_nodes
            WHERE workspace_id = :workspace_id AND embedding IS NOT NULL
            ORDER BY embedding <=> :embedding::vector
            LIMIT :top_k
            """
        ),
        {"embedding": vec_str, "workspace_id": workspace_id, "top_k": body.top_k},
    )
    rows = result.fetchall()
    return [
        {"id": str(r.id), "entity_name": r.entity_name, "entity_type": r.entity_type, "score": float(r.score)}
        for r in rows
    ]
