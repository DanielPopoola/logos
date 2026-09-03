.PHONY: help up down logs run worker

.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Start Postgres + Redis containers
	docker compose up -d

down: ## Stop containers
	docker compose down

logs: ## Tail container logs
	docker compose logs -f

run: ## Run the FastAPI dev server with reload
	uv run uvicorn app.main:app --reload

worker: ## Run the Celery worker
	uv run celery -A app.workers.celery_app worker --loglevel=info
