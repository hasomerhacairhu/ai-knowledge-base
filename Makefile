.PHONY: help build up down logs restart clean ingest-sync ingest-process ingest-full api-test

help:
	@echo "AI Knowledge Base - Multi-Service Architecture"
	@echo ""
	@echo "Available commands:"
	@echo "  make build          - Build all Docker images"
	@echo "  make up             - Start all services"
	@echo "  make down           - Stop all services"
	@echo "  make logs           - View logs from all services"
	@echo "  make restart        - Restart all services"
	@echo "  make clean          - Remove all containers and volumes"
	@echo ""
	@echo "Ingestion commands:"
	@echo "  make ingest-sync    - Sync files from Drive (max 10 files)"
	@echo "  make ingest-process - Process files with Unstructured"
	@echo "  make ingest-full    - Run full pipeline"
	@echo "  make ingest-stats   - Show pipeline statistics"
	@echo ""
	@echo "API commands:"
	@echo "  make api-test       - Test API health"
	@echo "  make api-search     - Example search query"
	@echo ""
	@echo "Development commands:"
	@echo "  make dev-api        - Run API locally (no Docker)"
	@echo "  make dev-ingest     - Run ingest locally (no Docker)"

# Docker Compose commands
build:
	docker-compose build

up:
	docker-compose up -d
	@echo "Services started. API available at http://localhost:8000"

down:
	docker-compose down

logs:
	docker-compose logs -f

restart:
	docker-compose restart

clean:
	docker-compose down -v
	@echo "All containers and volumes removed"

# Ingestion commands
ingest-sync:
	docker-compose run --rm ingest python main.py sync --max-files 10

ingest-process:
	docker-compose run --rm ingest python main.py process --max-files 10

ingest-full:
	docker-compose run --rm ingest python main.py full --max-files 10

ingest-stats:
	docker-compose run --rm ingest python main.py stats

# API commands
api-test:
	@curl -s http://localhost:8000/health | jq .

api-search:
	@curl -s -X POST http://localhost:8000/api/search \
		-H "Content-Type: application/json" \
		-d '{"query": "test", "max_results": 3}' | jq .

# Development commands (local, no Docker)
dev-api:
	cd services/api && uv run uvicorn main:app --reload --port 8000

dev-ingest:
	cd services/ingest && uv run python main.py sync --max-files 5
