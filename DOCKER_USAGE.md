# Docker Usage Guide

## Quick Start

### Build the containers
```bash
docker compose build
```

### Start PostgreSQL
```bash
docker compose up -d postgres
```

### Check pipeline statistics
```bash
docker compose run --rm ingest /app/.venv/bin/python main.py stats
```

## Running the Pipeline

### Full pipeline (sync → process → index)
```bash
# Process 10 files
docker compose run --rm ingest /app/.venv/bin/python main.py --max-files 10

# Process 100 files
docker compose run --rm ingest /app/.venv/bin/python main.py --max-files 100

# Full sync (no limit)
docker compose run --rm ingest /app/.venv/bin/python main.py
```

### Individual stages

#### Sync only
```bash
docker compose run --rm ingest /app/.venv/bin/python main.py sync --max-files 20
```

#### Process only
```bash
docker compose run --rm ingest /app/.venv/bin/python main.py process --max-files 20
```

#### Index only
```bash
docker compose run --rm ingest /app/.venv/bin/python main.py index --max-files 20
```

## Purge Operations

### Dry run (see what would be deleted)
```bash
docker compose run --rm ingest /app/.venv/bin/python purge.py --dry-run
```

### Full purge (requires confirmation)
```bash
docker compose run --rm ingest /app/.venv/bin/python purge.py
```

### Auto-confirm purge (dangerous!)
```bash
docker compose run --rm ingest /app/.venv/bin/python purge.py --yes
```

### Purge specific components
```bash
# S3 only
docker compose run --rm ingest /app/.venv/bin/python purge.py --s3-only --yes

# Database only
docker compose run --rm ingest /app/.venv/bin/python purge.py --db-only --yes

# Vector Store only
docker compose run --rm ingest /app/.venv/bin/python purge.py --vector-store-only --yes
```

## Environment Configuration

The Docker container uses these environment variables (set in `.env`):

- `POSTGRES_HOST=postgres` (overridden in docker-compose.yml)
- `POSTGRES_PORT=5432`
- `POSTGRES_DB=ai_knowledge_base`
- `POSTGRES_USER=postgres`
- `POSTGRES_PASSWORD=postgres`
- `GOOGLE_SERVICE_ACCOUNT_FILE=/app/service-account.json` (overridden in docker-compose.yml)
- All other `.env` variables (S3, OpenAI, etc.)

## Installed Dependencies

The Docker image includes:
- Python 3.11
- Tesseract OCR with languages: eng, hun, ces, slk, pol, deu, fra, spa, ita, ron
- poppler-utils (for PDF handling)
- libmagic (for file type detection)
- All Python dependencies from `pyproject.toml`

## Volume Mounts

- `/app/service-account.json` - Google Service Account credentials (read-only)
- `/app/data` - Shared data volume (not currently used)

## Troubleshooting

### Container can't connect to PostgreSQL
```bash
# Check PostgreSQL is running
docker compose ps

# Start PostgreSQL if not running
docker compose up -d postgres

# Check logs
docker compose logs postgres
```

### Service account file not found
Make sure the path in `.env` points to the correct local file. The docker-compose.yml will mount it to `/app/service-account.json`.

### Out of memory
If processing large PDFs with OCR, increase Docker's memory limit in Docker Desktop settings (minimum 4GB recommended, 8GB for optimal performance).

## Production Deployment

For production use with Portainer:

1. Build the image: `docker compose build ingest`
2. Push to registry (optional): `docker tag ai-kb-ingest:latest your-registry/ai-kb-ingest:latest`
3. Create Portainer Stack using `docker-compose.yml`
4. Configure environment variables in Portainer
5. Set up scheduled jobs for automatic ingestion
