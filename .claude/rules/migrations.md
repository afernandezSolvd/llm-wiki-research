---
globs: alembic/versions/**/*.py
---
# Migration Rules

- Never edit existing migration files — create new revisions instead.
- Always include `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` in
  the first migration of any new database.
- HNSW indexes must specify:
    postgresql_using="hnsw",
    postgresql_with={"m": 16, "ef_construction": 64},
    postgresql_ops={"column_name": "vector_cosine_ops"}
- Test that downgrade() actually reverses upgrade() — they must be symmetric.
- Vector columns use Vector(1024) — always 1024 dimensions to match voyage-3-large.
- After generating a migration with --autogenerate, review it before applying —
  autogenerate misses server_default changes and some index types.
