"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1024


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.Text, nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_platform_admin", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── workspaces ────────────────────────────────────────────────────────────
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("git_repo_path", sa.Text, nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("settings", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_workspaces_slug", "workspaces", ["slug"], unique=True)

    # ── user_workspace_memberships ────────────────────────────────────────────
    op.create_table(
        "user_workspace_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "workspace_id"),
    )

    # ── sources ───────────────────────────────────────────────────────────────
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), unique=True),
        sa.Column("byte_size", sa.BigInteger),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("ingest_status", sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sources_workspace_id", "sources", ["workspace_id"])

    # ── source_chunks ─────────────────────────────────────────────────────────
    op.create_table(
        "source_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.Column("created_at", sa.String),
        sa.UniqueConstraint("source_id", "chunk_index"),
    )
    op.create_index("ix_source_chunks_source_id", "source_chunks", ["source_id"])
    op.create_index("ix_source_chunks_workspace_id", "source_chunks", ["workspace_id"])
    op.execute(
        f"CREATE INDEX ix_source_chunks_embedding_hnsw ON source_chunks "
        f"USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)"
    )

    # ── wiki_pages ────────────────────────────────────────────────────────────
    op.create_table(
        "wiki_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_path", sa.Text, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("page_type", sa.String(30), nullable=False),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("git_commit_sha", sa.String(40)),
        sa.Column("word_count", sa.Integer),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.Column("last_lint_at", sa.String),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_wiki_pages_workspace_path", "wiki_pages", ["workspace_id", "page_path"], unique=True)
    op.execute(
        f"CREATE INDEX ix_wiki_pages_embedding_hnsw ON wiki_pages "
        f"USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)"
    )

    # ── wiki_page_versions ────────────────────────────────────────────────────
    op.create_table(
        "wiki_page_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("wiki_page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wiki_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("git_commit_sha", sa.String(40), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("diff_from_prev", sa.Text),
        sa.Column("semantic_drift_score", sa.Float),
        sa.Column("change_reason", sa.String(255)),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.String, nullable=False),
    )
    op.create_index("ix_wiki_page_versions_page_created", "wiki_page_versions", ["wiki_page_id", "created_at"])

    # ── schema_configs ────────────────────────────────────────────────────────
    op.create_table(
        "schema_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("cache_control", sa.String(20), nullable=False, server_default="'ephemeral'"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── ingest_jobs ───────────────────────────────────────────────────────────
    op.create_table(
        "ingest_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("celery_task_id", sa.String(255)),
        sa.Column("status", sa.String(20), nullable=False, server_default="'queued'"),
        sa.Column("source_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
        sa.Column("pages_touched", postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
        sa.Column("llm_tokens_used", sa.Integer),
        sa.Column("llm_cost_usd", sa.Numeric(10, 6)),
        sa.Column("error_message", sa.Text),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("started_at", sa.String),
        sa.Column("completed_at", sa.String),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ingest_jobs_workspace_id", "ingest_jobs", ["workspace_id"])
    op.create_index("ix_ingest_jobs_status", "ingest_jobs", ["status"])

    # ── lint_runs ─────────────────────────────────────────────────────────────
    op.create_table(
        "lint_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("celery_task_id", sa.String(255)),
        sa.Column("status", sa.String(20), nullable=False, server_default="'queued'"),
        sa.Column("scope", sa.String(20), nullable=False, server_default="'full'"),
        sa.Column("page_ids_scoped", postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
        sa.Column("finding_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("auto_fixed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("completed_at", sa.String),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── lint_findings ─────────────────────────────────────────────────────────
    op.create_table(
        "lint_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("lint_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lint_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("wiki_page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wiki_pages.id", ondelete="SET NULL")),
        sa.Column("finding_type", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("evidence", postgresql.JSONB),
        sa.Column("auto_fix_applied", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("fix_commit_sha", sa.String(40)),
        sa.Column("created_at", sa.String, nullable=False),
    )
    op.create_index("ix_lint_findings_lint_run_id", "lint_findings", ["lint_run_id"])

    # ── kg_communities ────────────────────────────────────────────────────────
    op.create_table(
        "kg_communities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("member_count", sa.Integer),
        sa.Column("summary", sa.Text),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.Column("parent_community_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kg_communities.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_kg_communities_workspace_id", "kg_communities", ["workspace_id"])

    # ── kg_nodes ──────────────────────────────────────────────────────────────
    op.create_table(
        "kg_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_name", sa.String(500), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.Text)),
        sa.Column("wiki_page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wiki_pages.id", ondelete="SET NULL")),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.Column("source_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
        sa.Column("community_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kg_communities.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_kg_nodes_workspace_id", "kg_nodes", ["workspace_id"])
    op.create_index("uq_kg_nodes_workspace_name_type", "kg_nodes", ["workspace_id", "entity_name", "entity_type"], unique=True)
    op.execute(
        "CREATE INDEX ix_kg_nodes_embedding_hnsw ON kg_nodes "
        "USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)"
    )

    # ── kg_edges ──────────────────────────────────────────────────────────────
    op.create_table(
        "kg_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kg_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kg_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(50), nullable=False),
        sa.Column("weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("evidence", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_kg_edges_workspace_source", "kg_edges", ["workspace_id", "source_node_id", "relation_type"])
    op.create_index("ix_kg_edges_workspace_target", "kg_edges", ["workspace_id", "target_node_id"])

    # ── audit_logs ────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True)),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50)),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("old_value", postgresql.JSONB),
        sa.Column("new_value", postgresql.JSONB),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.Text),
        sa.Column("created_at", sa.String, nullable=False),
    )
    op.create_index("ix_audit_logs_workspace_created", "audit_logs", ["workspace_id", "created_at"])
    op.create_index("ix_audit_logs_user_created", "audit_logs", ["user_id", "created_at"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade() -> None:
    for table in [
        "audit_logs", "kg_edges", "kg_nodes", "kg_communities",
        "lint_findings", "lint_runs", "ingest_jobs", "schema_configs",
        "wiki_page_versions", "wiki_pages", "source_chunks", "sources",
        "user_workspace_memberships", "workspaces", "users",
    ]:
        op.drop_table(table)
