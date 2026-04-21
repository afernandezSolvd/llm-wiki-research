import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.source import EMBEDDING_DIM


class KGCommunity(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "kg_communities"

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    member_count: Mapped[int | None] = mapped_column()
    summary: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    parent_community_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kg_communities.id", ondelete="SET NULL")
    )

    nodes: Mapped[list["KGNode"]] = relationship(back_populates="community")


class KGNode(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "kg_nodes"
    __table_args__ = (
        Index("uq_kg_nodes_workspace_name_type", "workspace_id", "entity_name", "entity_type", unique=True),
        Index(
            "ix_kg_nodes_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    entity_name: Mapped[str] = mapped_column(String(500), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    aliases: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    wiki_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wiki_pages.id", ondelete="SET NULL")
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    source_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    community_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kg_communities.id", ondelete="SET NULL")
    )

    community: Mapped["KGCommunity | None"] = relationship(back_populates="nodes")
    outgoing_edges: Mapped[list["KGEdge"]] = relationship(
        back_populates="source_node",
        foreign_keys="KGEdge.source_node_id",
        cascade="all, delete-orphan",
    )
    incoming_edges: Mapped[list["KGEdge"]] = relationship(
        back_populates="target_node",
        foreign_keys="KGEdge.target_node_id",
        cascade="all, delete-orphan",
    )


class KGEdge(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "kg_edges"
    __table_args__ = (
        Index("ix_kg_edges_workspace_source", "workspace_id", "source_node_id", "relation_type"),
        Index("ix_kg_edges_workspace_target", "workspace_id", "target_node_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kg_nodes.id", ondelete="CASCADE"), nullable=False
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kg_nodes.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSONB)

    source_node: Mapped["KGNode"] = relationship(back_populates="outgoing_edges", foreign_keys=[source_node_id])
    target_node: Mapped["KGNode"] = relationship(back_populates="incoming_edges", foreign_keys=[target_node_id])
