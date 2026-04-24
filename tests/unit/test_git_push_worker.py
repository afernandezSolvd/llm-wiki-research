"""Unit tests for git_push_worker — no DB, no real Redis, no real git."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


WORKSPACE_ID = str(uuid.uuid4())


def _make_workspace(remote_url="https://github.com/org/repo.git"):
    ws = MagicMock()
    ws.id = uuid.UUID(WORKSPACE_ID)
    ws.git_remote_url = remote_url
    ws.git_last_push_at = None
    ws.git_last_push_error = None
    return ws


def _db_ctx(workspace):
    """Return a context manager mock that yields a db session returning workspace."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = workspace
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    session_factory = MagicMock(return_value=db)
    return session_factory


def _redis_mock(lock_acquired=True):
    redis_client = AsyncMock()
    redis_client.set = AsyncMock(return_value=True if lock_acquired else None)
    redis_client.delete = AsyncMock()
    redis_client.aclose = AsyncMock()
    return redis_client


def _settings(enabled=True):
    s = MagicMock()
    s.wiki_git_enabled = enabled
    s.redis_url = "redis://localhost:6379/0"
    s.database_url = "postgresql+asyncpg://test"
    s.wiki_git_provider_token = "ghp_test"
    return s


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_push_success_clears_error_and_sets_timestamp():
    workspace = _make_workspace()
    session_factory = _db_ctx(workspace)
    redis_client = _redis_mock(lock_acquired=True)

    with (
        patch("app.config.get_settings", return_value=_settings()),
        patch("sqlalchemy.ext.asyncio.create_async_engine"),
        patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=session_factory),
        patch("app.git.repo_manager.RepoManager") as MockRM,
        patch("redis.asyncio.from_url", return_value=redis_client),
    ):
        mock_repo = MagicMock()
        mock_repo.push_to_remote.return_value = "abc1234def5678"
        MockRM.return_value = mock_repo

        from app.workers.git_push_worker import _push_async
        await _push_async(WORKSPACE_ID)

    mock_repo.push_to_remote.assert_called_once_with("ghp_test")
    assert workspace.git_last_push_at is not None
    assert workspace.git_last_push_error is None
    redis_client.delete.assert_called_once()


@pytest.mark.asyncio
async def test_push_failure_sets_error_does_not_suppress():
    workspace = _make_workspace()
    session_factory = _db_ctx(workspace)
    redis_client = _redis_mock(lock_acquired=True)

    with (
        patch("app.config.get_settings", return_value=_settings()),
        patch("sqlalchemy.ext.asyncio.create_async_engine"),
        patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=session_factory),
        patch("app.git.repo_manager.RepoManager") as MockRM,
        patch("redis.asyncio.from_url", return_value=redis_client),
    ):
        mock_repo = MagicMock()
        mock_repo.push_to_remote.side_effect = RuntimeError("401 Unauthorized")
        MockRM.return_value = mock_repo

        from app.workers.git_push_worker import _push_async
        with pytest.raises(RuntimeError, match="401 Unauthorized"):
            await _push_async(WORKSPACE_ID)

    assert workspace.git_last_push_error == "401 Unauthorized"
    redis_client.delete.assert_called_once()


@pytest.mark.asyncio
async def test_lock_unavailable_raises_lock_unavailable():
    workspace = _make_workspace()
    session_factory = _db_ctx(workspace)
    redis_client = _redis_mock(lock_acquired=False)

    with (
        patch("app.config.get_settings", return_value=_settings()),
        patch("sqlalchemy.ext.asyncio.create_async_engine"),
        patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=session_factory),
        patch("redis.asyncio.from_url", return_value=redis_client),
    ):
        from app.workers.git_push_worker import _LockUnavailable, _push_async
        with pytest.raises(_LockUnavailable):
            await _push_async(WORKSPACE_ID)


@pytest.mark.asyncio
async def test_wiki_git_disabled_skips_everything():
    with patch("app.config.get_settings", return_value=_settings(enabled=False)):
        from app.workers.git_push_worker import _push_async
        await _push_async(WORKSPACE_ID)
        # No exception — returns immediately


@pytest.mark.asyncio
async def test_null_git_remote_url_skips_lock():
    workspace = _make_workspace(remote_url=None)
    session_factory = _db_ctx(workspace)
    redis_client = _redis_mock()

    with (
        patch("app.config.get_settings", return_value=_settings()),
        patch("sqlalchemy.ext.asyncio.create_async_engine"),
        patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=session_factory),
        patch("redis.asyncio.from_url", return_value=redis_client),
    ):
        from app.workers.git_push_worker import _push_async
        await _push_async(WORKSPACE_ID)

    redis_client.set.assert_not_called()
