from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "llm_wiki",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.ingest_worker",
        "app.workers.lint_worker",
        "app.workers.embedding_worker",
        "app.workers.graph_worker",
        "app.workers.git_push_worker",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "app.workers.ingest_worker.*": {"queue": "ingest"},
        "app.workers.lint_worker.*": {"queue": "lint"},
        "app.workers.embedding_worker.*": {"queue": "embedding"},
        "app.workers.graph_worker.*": {"queue": "graph"},
        "app.workers.git_push_worker.*": {"queue": "git_push"},
    },
    beat_schedule={
        # Rebuild hot-pages cache every 15 minutes
        "rebuild-hot-pages-cache": {
            "task": "app.workers.graph_worker.refresh_hot_pages_all_workspaces",
            "schedule": crontab(minute="*/15"),
        },
    },
)
