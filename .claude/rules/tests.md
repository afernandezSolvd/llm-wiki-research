---
globs: tests/**/*.py
---
# Test Rules

- Unit tests (tests/unit/) must not import AsyncSessionLocal, get_redis_pool,
  or any external service. Mock at the function boundary if needed.
- Integration tests (tests/integration/) run against a real PostgreSQL
  instance — use the fixtures in conftest.py.
- Never mock _cosine_distance — test it with real vectors.
- All new workers must have at least one unit test covering the async helper's
  pure utility functions (e.g. _extract_text, _cosine_distance patterns).
- Test file names mirror source: app/workers/ingest_worker.py →
  tests/unit/test_ingest_worker.py
- Use pytest.mark.asyncio for async test functions.
