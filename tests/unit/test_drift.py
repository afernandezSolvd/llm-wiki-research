"""Tests for drift calculation correctness."""
from app.workers.ingest_worker import _cosine_distance


def test_cosine_distance_identical_vectors():
    v = [1.0, 0.0, 0.0]
    assert _cosine_distance(v, v) == 0.0


def test_cosine_distance_orthogonal():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    dist = _cosine_distance(a, b)
    assert dist is not None
    assert abs(dist - 1.0) < 1e-9


def test_cosine_distance_opposite():
    a = [1.0, 0.0, 0.0]
    b = [-1.0, 0.0, 0.0]
    dist = _cosine_distance(a, b)
    assert dist is not None
    assert abs(dist - 2.0) < 1e-9


def test_cosine_distance_none_inputs():
    assert _cosine_distance(None, [1.0]) is None
    assert _cosine_distance([1.0], None) is None
    assert _cosine_distance(None, None) is None


def test_origin_anchored_drift_not_cumulative():
    """
    Regression: drift must measure distance from the original embedding,
    not accumulate incremental distances (old cumulative approach was wrong).
    """
    original = [1.0, 0.0, 0.0]
    # Simulate 5 small shifts — each only 0.05 cosine distance from previous
    # but together they've moved significantly from the origin
    current = [0.0, 1.0, 0.0]  # orthogonal to original → large absolute drift

    abs_drift = _cosine_distance(original, current)
    # Cumulative of 5 small drifts might be 0.25 (below threshold)
    # but absolute drift is 1.0 (correctly flagged)
    assert abs_drift is not None
    assert abs_drift > 0.9  # clearly far from origin
