import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    memberships: Mapped[list["UserWorkspaceMembership"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="UserWorkspaceMembership.user_id",
    )


class UserWorkspaceMembership(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_workspace_memberships"
    __table_args__ = (UniqueConstraint("user_id", "workspace_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # admin|editor|reader
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    user: Mapped["User"] = relationship(back_populates="memberships", foreign_keys=[user_id])
    workspace: Mapped["Workspace"] = relationship(back_populates="memberships")  # type: ignore[name-defined]
