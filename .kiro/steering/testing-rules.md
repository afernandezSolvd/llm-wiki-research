# Testing Rules

## Unit Tests (tests/unit/)
- No database, no external services, no Redis, no Celery
- Import only pure functions: _cosine_distance, rrf_fuse, parse_lint_response,
  extract_wikilinks, _extract_text, etc.
- Mock at the service boundary when needed — never mock internal helpers
- Test normal inputs, edge cases (None, empty list, zero vector), boundaries

## Integration Tests (tests/integration/)
- Require running PostgreSQL (use docker-compose up db for CI)
- Use fixtures in tests/conftest.py for DB session and test workspace
- Each test cleans up after itself — use transactions that rollback, or
  truncate tables in a fixture teardown
- Never use production data

## Coverage Targets
- app/services/: >80%
- app/retrieval/: >80%
- app/llm/output_parsers/: >90% (pure parsing logic, easy to test)
- app/workers/: covered by integration tests, not unit mocks

## New Feature Rules
- Every new Celery worker task → unit tests for all pure utility functions
- Every new API endpoint → at least one integration test covering success + 403
- Every new output parser → unit tests with valid JSON, malformed JSON, empty

## Test File Naming
Mirror source file structure:
  app/workers/ingest_worker.py → tests/unit/test_ingest_worker.py
  app/retrieval/hybrid_ranker.py → tests/unit/test_hybrid_ranker.py

## Running Tests
- All tests: make test
- Unit only: pytest tests/unit/ -v
- Specific file: pytest tests/unit/test_drift.py -v
- With coverage HTML: pytest --cov=app --cov-report=html
