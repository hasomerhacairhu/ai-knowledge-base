.PHONY: help build up down logs restart clean ingest-sync ingest-process ingest-full api-test

help:
	@echo "AI Knowledge Base - Multi-Service Architecture"
	@echo ""
	@echo "Available commands:"
	@echo "  make build          - Build all Docker images (local builds)"
	@echo "  make up             - Start all services (local builds, default)"
	@echo "  make up-registry    - Start services with pre-built registry images (fastest)"
	@echo "  make up-local       - Start services with local builds (explicit)"
	@echo "  make down           - Stop all services"
	@echo ""
	@echo "CI Information:"
	@echo "  Registry images auto-build on code changes (optimized CI)"
	@echo "  See CI_OPTIMIZATION_GUIDE.md for trigger details"
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
	docker-compose up -d --build
	@echo "Services started with local builds. API available at http://localhost:8000"

up-registry:
	docker-compose -f docker-compose-from-registry.yml up -d
	@echo "Services started with registry images. API available at http://localhost:8000"

up-local:
	docker-compose -f docker-compose-local-builld.yml up -d --build
	@echo "Services started with local builds (explicit). API available at http://localhost:8000"

down:
	docker-compose down || true
	docker-compose -f docker-compose-from-registry.yml down || true
	docker-compose -f docker-compose-local-builld.yml down || true

logs:
	docker-compose logs -f

restart:
	docker-compose restart

clean:
	docker-compose down -v || true
	docker-compose -f docker-compose-from-registry.yml down -v || true
	docker-compose -f docker-compose-local-builld.yml down -v || true
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
