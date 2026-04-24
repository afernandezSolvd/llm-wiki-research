import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Workspace(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces"

    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    git_repo_path: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    deleted_at: Mapped[None] = mapped_column(DateTime(timezone=True), nullable=True)

    git_remote_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    git_last_push_at: Mapped[None] = mapped_column(DateTime(timezone=True), nullable=True)
    git_last_push_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    memberships: Mapped[list["UserWorkspaceMembership"]] = relationship(  # type: ignore[name-defined]
        back_populates="workspace", cascade="all, delete-orphan"
    )
    sources: Mapped[list["Source"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")  # type: ignore[name-defined]
    wiki_pages: Mapped[list["WikiPage"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")  # type: ignore[name-defined]
    schema_config: Mapped["SchemaConfig | None"] = relationship(back_populates="workspace", uselist=False)  # type: ignore[name-defined]
