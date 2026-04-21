.PHONY: up down migrate revision shell test lint

up:
	docker compose up -d db redis
	sleep 2
	$(MAKE) migrate
	docker compose up -d api worker beat flower

down:
	docker compose down

migrate:
	alembic upgrade head

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
