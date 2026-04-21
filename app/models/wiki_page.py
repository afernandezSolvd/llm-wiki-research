import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.source import EMBEDDING_DIM


class WikiPage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "wiki_pages"
    __table_args__ = (
        Index("ix_wiki_pages_workspace_path", "workspace_id", "page_path", unique=True),
        Index(
            "ix_wiki_pages_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    page_path: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    page_type: Mapped[str] = mapped_column(String(30), nullable=False)  # entity|concept|summary|exploration|index|log
    content_hash: Mapped[str | None] = mapped_column(String(64))
    git_commit_sha: Mapped[str | None] = mapped_column(String(40))
    word_count: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    # Original embedding set on page creation — never overwritten.
    # Drift = cosine_distance(original_embedding, embedding) gives absolute divergence.
    original_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    last_lint_at: Mapped[str | None] = mapped_column(String)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="wiki_pages")  # type: ignore[name-defined]
    versions: Mapped[list["WikiPageVersion"]] = relationship(
        back_populates="page", cascade="all, delete-orphan", order_by="WikiPageVersion.created_at.desc()"
    )


class WikiPageVersion(Base, UUIDMixin):
    __tablename__ = "wiki_page_versions"
    __table_args__ = (
        Index("ix_wiki_page_versions_page_created", "wiki_page_id", "created_at"),
    )

    wiki_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wiki_pages.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    git_commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    diff_from_prev: Mapped[str | None] = mapped_column(Text)
    semantic_drift_score: Mapped[float | None] = mapped_column(Float)
    change_reason: Mapped[str | None] = mapped_column(String(255))
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    page: Mapped["WikiPage"] = relationship(back_populates="versions")


class WikiPageSourceMap(Base, UUIDMixin, TimestampMixin):
    """
    Tracks which sources contributed to which wiki pages (and at what commit).
    Enables: "show me what source X wrote" and "undo contributions from source X".
    """
    __tablename__ = "wiki_page_source_map"
    __table_args__ = (
        UniqueConstraint("wiki_page_id", "source_id"),
        Index("ix_wiki_page_source_map_source", "source_id"),
        Index("ix_wiki_page_source_map_page", "wiki_page_id"),
    )

    wiki_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wiki_pages.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # The git commit that first introduced this source's contribution to the page
    first_commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    # Most recent commit where this source updated the page
    latest_commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
