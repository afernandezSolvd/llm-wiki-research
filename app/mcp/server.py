import uuid

import bcrypt
from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from app.core.logging import get_logger
from app.models.user import User

logger = get_logger(__name__)

mcp = FastMCP("context-wiki")

_MCP_SERVICE_EMAIL = "mcp-service@internal"


async def get_mcp_service_user(db) -> User:
    """Return the MCP service account (platform_admin), creating it on first call."""
    result = await db.execute(select(User).where(User.email == _MCP_SERVICE_EMAIL))
    user = result.scalar_one_or_none()
    if user is None:
        hashed = bcrypt.hashpw(uuid.uuid4().bytes, bcrypt.gensalt()).decode()
        user = User(
            email=_MCP_SERVICE_EMAIL,
            hashed_password=hashed,
            full_name="MCP Server (service account)",
            is_active=True,
            is_platform_admin=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("mcp.service_account_created", user_id=str(user.id))
    return user


def _register_tools() -> None:
    import app.mcp.tools.ingest  # noqa: F401
    import app.mcp.tools.meta  # noqa: F401
    import app.mcp.tools.quality  # noqa: F401
    import app.mcp.tools.query  # noqa: F401
    import app.mcp.tools.sources  # noqa: F401
    import app.mcp.tools.wiki  # noqa: F401
    import app.mcp.tools.workspaces  # noqa: F401


def run_stdio() -> None:
    _register_tools()
    mcp.run(transport="stdio")


def get_http_app():
    """Return a Starlette app for Streamable HTTP transport. Called by main.py."""
    _register_tools()
    return mcp.streamable_http_app()


if __name__ == "__main__":
    import sys as _sys

    _sys.modules.setdefault("app.mcp.server", _sys.modules["__main__"])
    run_stdio()
