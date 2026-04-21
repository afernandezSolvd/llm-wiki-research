import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class LintRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "lint_runs"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    scope: Mapped[str] = mapped_column(String(20), default="full", nullable=False)  # full|incremental|page_list
    page_ids_scoped: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    finding_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    auto_fixed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    completed_at: Mapped[str | None] = mapped_column(String)

    findings: Mapped[list["LintFinding"]] = relationship(
        back_populates="lint_run", cascade="all, delete-orphan"
    )


class LintFinding(Base, UUIDMixin):
    __tablename__ = "lint_findings"

    lint_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lint_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    wiki_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wiki_pages.id", ondelete="SET NULL")
    )
    finding_type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # error|warning|info
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSONB)
    auto_fix_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fix_commit_sha: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    lint_run: Mapped["LintRun"] = relationship(back_populates="findings")
