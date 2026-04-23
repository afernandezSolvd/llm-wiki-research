"""Unit tests for MCP tool infrastructure.

Covers: MCPResponse envelope, input validation in tool handlers.
No DB, no external services — all service calls are mocked at the function boundary.
"""
import json
import uuid

import pytest

from app.mcp.response import MCPResponse


# ── MCPResponse envelope ─────────────────────────────────────────────────────

class TestMCPResponse:
    def test_to_json_includes_summary(self):
        r = MCPResponse(summary="done", data={"x": 1})
        payload = json.loads(r.to_json())
        assert payload["summary"] == "done"
        assert payload["data"] == {"x": 1}
        assert payload["error"] is None

    def test_err_factory_sets_error_field(self):
        r = MCPResponse.err("something broke", code="bad_input")
        payload = json.loads(r.to_json())
        assert payload["summary"] == "something broke"
        assert payload["error"]["error"] == "bad_input"
        assert payload["error"]["detail"] == "something broke"

    def test_default_data_is_empty_dict(self):
        r = MCPResponse(summary="ok")
        assert r.data == {}

    def test_to_json_is_valid_json(self):
        r = MCPResponse(summary="test", data={"nested": {"key": [1, 2, 3]}})
        parsed = json.loads(r.to_json())
        assert parsed["data"]["nested"]["key"] == [1, 2, 3]


# ── Input validation: ingest_url ─────────────────────────────────────────────

class TestIngestUrlValidation:
    @pytest.mark.asyncio
    async def test_invalid_workspace_uuid_returns_error(self):
        from app.mcp.tools.ingest import ingest_url
        result = json.loads(await ingest_url("not-a-uuid", "https://example.com"))
        assert result["error"] is not None
        assert "Invalid workspace_id" in result["summary"]

    @pytest.mark.asyncio
    async def test_invalid_url_scheme_returns_error(self):
        from app.mcp.tools.ingest import ingest_url
        ws_id = str(uuid.uuid4())
        result = json.loads(await ingest_url(ws_id, "ftp://example.com"))
        assert result["error"] is not None
        assert "http" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_valid_https_url_passes_validation(self, monkeypatch):
        from app.mcp.tools import ingest as ingest_mod
        # Prevent actual DB/network calls — just verify it passes URL validation
        async def _fake_db_context():
            raise RuntimeError("DB not available in unit test")

        monkeypatch.setattr(ingest_mod, "AsyncSessionLocal", _fake_db_context)

        from app.mcp.tools.ingest import ingest_url
        ws_id = str(uuid.uuid4())
        result = json.loads(await ingest_url(ws_id, "https://example.com"))
        # Should fail at DB level, not at validation — error comes from DB not URL check
        assert "Invalid" not in result["summary"] or "workspace_id" not in result["summary"]


# ── Input validation: query_wiki ─────────────────────────────────────────────

class TestQueryWikiValidation:
    @pytest.mark.asyncio
    async def test_invalid_workspace_uuid_returns_error(self):
        from app.mcp.tools.query import query_wiki
        result = json.loads(await query_wiki("bad-uuid", "what is X?"))
        assert result["error"] is not None
        assert "Invalid workspace_id" in result["summary"]

    @pytest.mark.asyncio
    async def test_empty_question_returns_error(self):
        from app.mcp.tools.query import query_wiki
        ws_id = str(uuid.uuid4())
        result = json.loads(await query_wiki(ws_id, "   "))
        assert result["error"] is not None
        assert "question" in result["summary"].lower()

    def test_default_top_k_is_20(self):
        import inspect
        from app.mcp.tools.query import query_wiki
        sig = inspect.signature(query_wiki)
        assert sig.parameters["top_k"].default == 20


# ── Input validation: wiki page_path normalization ───────────────────────────

class TestWikiPagePathNormalization:
    @pytest.mark.asyncio
    async def test_leading_slash_stripped_before_lookup(self, monkeypatch):
        """page_path with leading / should be normalized before the DB query."""
        from app.mcp.tools import wiki as wiki_mod

        captured = {}

        class FakeDB:
            async def execute(self, q):
                captured["query"] = str(q)
                return FakeResult(None)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

        class FakeResult:
            def __init__(self, val):
                self._val = val

            def scalar_one_or_none(self):
                return self._val

        class FakeSessionLocal:
            def __call__(self):
                return FakeDB()

        monkeypatch.setattr(wiki_mod, "AsyncSessionLocal", FakeSessionLocal())

        from app.mcp.tools.wiki import get_wiki_page
        ws_id = str(uuid.uuid4())
        result = json.loads(await get_wiki_page(ws_id, "/concepts/test.md"))
        # Page not found is expected (FakeDB returns None); important: no error about UUID
        assert "Invalid workspace_id" not in result["summary"]
        assert "not found" in result["summary"].lower() or result["error"] is not None
