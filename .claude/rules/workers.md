---
globs: app/workers/**/*.py
---
# Worker Rules

- Every Celery task function must be sync (def, not async def).
  Use the `_run(coro)` helper which calls `asyncio.run()`.
- All imports from app.* must be INSIDE the async helper function,
  not at module level, to prevent circular import issues at worker startup.
- Never use `asyncio.get_event_loop()` — always `asyncio.run()` in tasks
  and `asyncio.get_running_loop()` inside async functions.
- Retry counts: ingest max_retries=3, lint max_retries=2.
- Always call `_mark_job_failed` / `_mark_run_failed` before re-raising.
- Worker task names must match the module path exactly:
  name="app.workers.{module}.{function}"
