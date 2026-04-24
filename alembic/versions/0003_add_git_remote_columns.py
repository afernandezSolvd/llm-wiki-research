"""add git remote columns to workspaces

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("git_remote_url", sa.Text(), nullable=True))
    op.add_column(
        "workspaces",
        sa.Column("git_last_push_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workspaces", sa.Column("git_last_push_error", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("workspaces", "git_last_push_error")
    op.drop_column("workspaces", "git_last_push_at")
    op.drop_column("workspaces", "git_remote_url")
