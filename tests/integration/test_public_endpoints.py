"""Integration tests for the public read-only portal API.

Requires a running PostgreSQL instance (uses fixtures from conftest.py).
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source
from app.models.wiki_page import WikiPage, WikiPageSourceMap
from app.models.workspace import Workspace

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_workspace(db: AsyncSession, slug: str = None) -> Workspace:
    slug = slug or f"ws-{uuid.uuid4().hex[:8]}"
    ws = Workspace(
        slug=slug,
        display_name=f"Test Workspace {slug}",
        git_repo_path=f"/tmp/wiki_repos/{slug}",
    )
    db.add(ws)
    await db.flush()
    return ws


async def _create_page(db: AsyncSession, ws: Workspace, path: str = "test/page") -> WikiPage:
    page = WikiPage(
        workspace_id=ws.id,
        page_path=path,
        title=f"Page {path}",
        page_type="concept",
        content_hash="abc123",
        git_commit_sha="deadbeef",
        word_count=42,
    )
    db.add(page)
    await db.flush()
    return page


async def _create_source(db: AsyncSession, ws: Workspace, status: str = "completed") -> Source:
    src = Source(
        workspace_id=ws.id,
        title="test-source.pdf",
        source_type="pdf",
        storage_key="test/key",
        content_hash=f"hash-{uuid.uuid4().hex}",
        byte_size=1024,
        ingest_status=status,
    )
    db.add(src)
    await db.flush()
    return src


# ---------------------------------------------------------------------------
# List workspaces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_workspaces_returns_200(client: AsyncClient, db: AsyncSession):
    await _create_workspace(db)
    resp = await client.get("/api/v1/public/workspaces")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_workspaces_fields(client: AsyncClient, db: AsyncSession):
    ws = await _create_workspace(db, slug="field-check")
    resp = await client.get("/api/v1/public/workspaces")
    assert resp.status_code == 200
    ids = [w["id"] for w in resp.json()]
    assert str(ws.id) in ids
    entry = next(w for w in resp.json() if w["id"] == str(ws.id))
    assert "slug" in entry
    assert "display_name" in entry
    assert "schema_version" in entry


# ---------------------------------------------------------------------------
# List pages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pages_returns_200(client: AsyncClient, db: AsyncSession):
    ws = await _create_workspace(db)
    await _create_page(db, ws)
    resp = await client.get(f"/api/v1/public/workspaces/{ws.id}/pages")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_list_pages_unknown_workspace_returns_404(client: AsyncClient):
    resp = await client.get(f"/api/v1/public/workspaces/{uuid.uuid4()}/pages")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_pages_page_type_filter(client: AsyncClient, db: AsyncSession):
    ws = await _create_workspace(db)
    await _create_page(db, ws, "p/concept")
    resp = await client.get(f"/api/v1/public/workspaces/{ws.id}/pages?page_type=concept")
    assert resp.status_code == 200
    for p in resp.json():
        assert p["page_type"] == "concept"


# ---------------------------------------------------------------------------
# Get single page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_page_unknown_returns_404(client: AsyncClient, db: AsyncSession):
    ws = await _create_workspace(db)
    resp = await client.get(f"/api/v1/public/workspaces/{ws.id}/pages/no/such/page")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_page_unknown_workspace_returns_404(client: AsyncClient):
    resp = await client.get(f"/api/v1/public/workspaces/{uuid.uuid4()}/pages/any/path")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# List sources
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sources_returns_200(client: AsyncClient, db: AsyncSession):
    ws = await _create_workspace(db)
    await _create_source(db, ws)
    resp = await client.get(f"/api/v1/public/workspaces/{ws.id}/sources")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_list_sources_has_created_at(client: AsyncClient, db: AsyncSession):
    ws = await _create_workspace(db)
    await _create_source(db, ws)
    resp = await client.get(f"/api/v1/public/workspaces/{ws.id}/sources")
    assert resp.status_code == 200
    assert all("created_at" in s for s in resp.json())


@pytest.mark.asyncio
async def test_list_sources_status_filter(client: AsyncClient, db: AsyncSession):
    ws = await _create_workspace(db)
    await _create_source(db, ws, status="failed")
    await _create_source(db, ws, status="completed")
    resp = await client.get(f"/api/v1/public/workspaces/{ws.id}/sources?status_filter=failed")
    assert resp.status_code == 200
    for s in resp.json():
        assert s["ingest_status"] == "failed"


@pytest.mark.asyncio
async def test_list_sources_unknown_workspace_returns_404(client: AsyncClient):
    resp = await client.get(f"/api/v1/public/workspaces/{uuid.uuid4()}/sources")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Source → pages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_pages_returns_linked_pages(client: AsyncClient, db: AsyncSession):
    ws = await _create_workspace(db)
    src = await _create_source(db, ws)
    page = await _create_page(db, ws, "linked/page")
    db.add(WikiPageSourceMap(wiki_page_id=page.id, source_id=src.id))
    await db.flush()

    resp = await client.get(f"/api/v1/public/workspaces/{ws.id}/sources/{src.id}/pages")
    assert resp.status_code == 200
    paths = [p["page_path"] for p in resp.json()]
    assert "linked/page" in paths


@pytest.mark.asyncio
async def test_source_pages_unknown_source_returns_404(client: AsyncClient, db: AsyncSession):
    ws = await _create_workspace(db)
    resp = await client.get(f"/api/v1/public/workspaces/{ws.id}/sources/{uuid.uuid4()}/pages")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_short_query_returns_400(client: AsyncClient, db: AsyncSession):
    ws = await _create_workspace(db)
    resp = await client.get(f"/api/v1/public/workspaces/{ws.id}/search?q=x")
    assert resp.status_code == 422  # Pydantic min_length=2 → 422 Unprocessable Entity


@pytest.mark.asyncio
async def test_search_missing_q_returns_422(client: AsyncClient, db: AsyncSession):
    ws = await _create_workspace(db)
    resp = await client.get(f"/api/v1/public/workspaces/{ws.id}/search")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_returns_structure(client: AsyncClient, db: AsyncSession):
    ws = await _create_workspace(db)
    resp = await client.get(f"/api/v1/public/workspaces/{ws.id}/search?q=test")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_count" in body
    assert "results" in body
    assert isinstance(body["results"], list)


@pytest.mark.asyncio
async def test_search_unknown_workspace_returns_404(client: AsyncClient):
    resp = await client.get(f"/api/v1/public/workspaces/{uuid.uuid4()}/search?q=hello")
    assert resp.status_code == 404
