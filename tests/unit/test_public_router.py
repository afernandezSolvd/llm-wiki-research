"""Unit tests for pure helpers in app/api/v1/public.py.

Per Constitution VI: no AsyncSessionLocal, no external services.
"""
from app.api.v1.public import _make_snippet


def test_make_snippet_term_in_middle():
    content = "a" * 100 + "hello world" + "b" * 200
    snippet = _make_snippet(content, "hello")
    assert "hello" in snippet
    assert len(snippet) <= 310  # 300 chars + ellipsis markers


def test_make_snippet_term_at_start():
    content = "hello world " + "x" * 500
    snippet = _make_snippet(content, "hello")
    assert snippet.startswith("hello")


def test_make_snippet_term_not_found_returns_start():
    content = "the quick brown fox"
    snippet = _make_snippet(content, "zzz")
    assert snippet == content  # short enough to return fully


def test_make_snippet_short_content():
    content = "short text"
    snippet = _make_snippet(content, "short")
    assert snippet == content


def test_make_snippet_case_insensitive():
    content = "The QUICK brown fox jumps"
    snippet = _make_snippet(content, "quick")
    assert "QUICK" in snippet


def test_make_snippet_appends_ellipsis_when_truncated():
    content = "x" * 500
    snippet = _make_snippet(content, "x")
    assert snippet.endswith("…")


def test_public_api_disabled_guard(monkeypatch):
    """When PUBLIC_API_ENABLED=false the guard raises HTTPException(503)."""
    import pytest
    from fastapi import HTTPException

    from app.api.v1.public import _guard
    from app.config import Settings

    monkeypatch.setattr(
        "app.api.v1.public.get_settings",
        lambda: Settings(public_api_enabled=False),
    )
    with pytest.raises(HTTPException) as exc_info:
        _guard()
    assert exc_info.value.status_code == 503


def test_public_api_enabled_guard_passes(monkeypatch):
    from app.api.v1.public import _guard
    from app.config import Settings

    monkeypatch.setattr(
        "app.api.v1.public.get_settings",
        lambda: Settings(public_api_enabled=True),
    )
    _guard()  # should not raise
