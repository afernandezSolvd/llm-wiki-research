"""Unit tests for RRF hybrid ranker."""
import uuid

import pytest

from app.retrieval.hybrid_ranker import rrf_fuse
from app.retrieval.vector_search import SearchHit


def make_hit(page_id: uuid.UUID, score: float, source: str = "wiki_page") -> SearchHit:
    return SearchHit(
        page_id=page_id,
        chunk_id=None,
        page_path=f"pages/{page_id}.md",
        title="Test Page",
        excerpt="",
        score=score,
        source=source,
    )


def test_rrf_fuse_combines_lists():
    ids = [uuid.uuid4() for _ in range(5)]
    vector_hits = [make_hit(ids[i], 0.9 - i * 0.1) for i in range(4)]
    graph_hits = [make_hit(ids[2], 0.8), make_hit(ids[4], 0.7)]  # ids[2] appears in both

    fused = rrf_fuse(vector_hits, graph_hits, top_k=5)

    # ids[2] appears in both lists → should rank higher
    fused_ids = [h.page_id for h in fused]
    assert ids[2] in fused_ids
    pos_2 = fused_ids.index(ids[2])
    assert pos_2 <= 1  # should be in top 2


def test_rrf_fuse_deduplicates():
    page_id = uuid.uuid4()
    hits_a = [make_hit(page_id, 0.9)]
    hits_b = [make_hit(page_id, 0.8)]
    fused = rrf_fuse(hits_a, hits_b, top_k=10)
    # Should appear once
    assert len([h for h in fused if h.page_id == page_id]) == 1


def test_rrf_fuse_respects_top_k():
    ids = [uuid.uuid4() for _ in range(10)]
    hits = [make_hit(i, 1.0) for i in ids]
    fused = rrf_fuse(hits, top_k=3)
    assert len(fused) == 3


def test_rrf_fuse_empty():
    assert rrf_fuse([], []) == []
