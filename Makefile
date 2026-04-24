.PHONY: up down migrate revision shell test lint

up:
	docker compose up -d

down:
	docker compose down

migrate:
	docker compose run --rm migrate

revision:
	alembic revision --autogenerate -m "$(msg)"

shell:
	docker compose exec api python -c "import asyncio; from app.core.db import get_db; print('ok')"

test:
	pytest tests/ -v --cov=app --cov-report=term-missing

lint:
	ruff check app/ tests/
	mypy app/

dev:
	uvicorn app.main:app --reload --port 8000
