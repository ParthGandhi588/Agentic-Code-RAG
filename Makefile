.PHONY: install dev test test-cov lint format clean docker-up docker-down

install:
	uv sync --extra dev

dev:
	uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ -v --cov=src --cov-report=term-missing

lint:
	uv run ruff check src tests
	uv run mypy src

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov

docker-up:
	docker compose up -d

docker-down:
	docker compose down
