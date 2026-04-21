"""Add original_embedding to wiki_pages, wiki_page_source_map table

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1024


def upgrade() -> None:
    # original_embedding: set on page creation, never overwritten.
    # Absolute drift = cosine_distance(original_embedding, embedding).
    op.add_column(
        "wiki_pages",
        sa.Column("original_embedding", Vector(EMBEDDING_DIM), nullable=True),
    )

    # Provenance: which source contributed to which page
    op.create_table(
        "wiki_page_source_map",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "wiki_page_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wiki_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("first_commit_sha", sa.String(40), nullable=False),
        sa.Column("latest_commit_sha", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("wiki_page_id", "source_id"),
    )
    op.create_index("ix_wiki_page_source_map_source", "wiki_page_source_map", ["source_id"])
    op.create_index("ix_wiki_page_source_map_page", "wiki_page_source_map", ["wiki_page_id"])
    op.create_index(
        "ix_wiki_page_source_map_workspace", "wiki_page_source_map", ["workspace_id"]
    )


def downgrade() -> None:
    op.drop_table("wiki_page_source_map")
    op.drop_column("wiki_pages", "original_embedding")
