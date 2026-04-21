"""Reciprocal Rank Fusion (RRF) for combining vector + graph search results."""
from collections import defaultdict

from app.retrieval.vector_search import SearchHit


def rrf_fuse(
    *result_lists: list[SearchHit],
    k: int = 60,
    top_k: int = 20,
) -> list[SearchHit]:
    """
    Fuse multiple ranked lists using Reciprocal Rank Fusion.

    RRF score = sum(1 / (k + rank)) across all lists.
    k=60 is the standard constant that balances high-rank rewards.
    """
    scores: dict[str, float] = defaultdict(float)
    hit_map: dict[str, SearchHit] = {}

    for hit_list in result_lists:
        for rank, hit in enumerate(hit_list):
            # Use page_id as key if available, else chunk_id
            key = str(hit.page_id or hit.chunk_id)
            scores[key] += 1.0 / (k + rank + 1)
            if key not in hit_map:
                hit_map[key] = hit

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [hit_map[key] for key, _ in fused]


def deduplicate_wiki_hits(hits: list[SearchHit]) -> list[SearchHit]:
    """Remove duplicate wiki page hits, keeping highest-scored."""
    seen: set[str] = set()
    result = []
    for hit in hits:
        key = str(hit.page_id)
        if key not in seen:
            seen.add(key)
            result.append(hit)
    return result
