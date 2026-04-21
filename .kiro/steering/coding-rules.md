# Coding Rules

## Async / Celery Pattern (CRITICAL)
Celery task functions are SYNC (def, not async def). They call `asyncio.run()`
via the `_run()` helper. Never use `asyncio.get_event_loop()` — it is
deprecated in Python 3.10+ and fails in Celery's thread context.

Correct pattern:
```python
def _run(coro):
    return asyncio.run(coro)

@celery_app.task(name="app.workers.my_worker.my_task", bind=True)
def my_task(self, id: str):
    _run(_my_task_async(uuid.UUID(id)))

async def _my_task_async(id: uuid.UUID):
    from app.core.db import AsyncSessionLocal   # import INSIDE async fn
    async with AsyncSessionLocal() as db:
        ...
```

## Prompt Templates (CRITICAL)
ALL prompt templates use `${var}` placeholders replaced with `.replace()`.
Never use Python `.format()` or f-strings with user content — source
documents may contain literal `{` and `}` characters that cause KeyError.

Correct:
```python
user_text = (
    TEMPLATE
    .replace("${question}", question)
    .replace("${context}", ctx)
)
```

Wrong:
```python
user_text = TEMPLATE.format(question=question)  # KeyError if question has {}
```

## Imports in Workers
All `app.*` imports must be INSIDE the async helper function body.
This prevents circular imports at Celery worker startup time.

## Redis
`get_redis_pool()` is decorated with `@lru_cache` and returns synchronously.
Never `await get_redis_pool()`. Always call it as a plain function.

## Drift Measurement
`original_embedding` on WikiPage is set ONCE at page creation and never
updated. It is the absolute drift baseline.
Drift = cosine_distance(original_embedding, current_embedding).
Never sum incremental drifts — always compare against the original.

## API Keys
Voyage AI (embeddings) and Anthropic (LLM) are completely separate services:
- VOYAGE_API_KEY → voyageai.Client(api_key=...)
- ANTHROPIC_API_KEY → Anthropic(api_key=...)
Never pass one to the other.

## Logging
Use structured logging only:
```python
logger.info("event_name", key=value, other_key=other_value)
```
Never use f-strings in log messages. Event names use snake_case.
