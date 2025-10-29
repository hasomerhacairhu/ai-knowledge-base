# AI Knowledge Base - Multi-Service Architecture# AI Knowledge Base - Multi-Service Architecture# AI Knowledge Base Ingest Pipeline



A modular document ingestion and search system with separate Docker services for ingestion, API, and PostgreSQL database.



## 🏗️ ArchitectureA modular document ingestion and search system with separate Docker services for ingestion, API, and database.A robust document ingestion pipeline that syncs documents from Google Drive, processes them with Unstructured.io, stores them in S3, and indexes them in OpenAI Vector Stores for semantic search.



```

┌─────────────────┐

│  Google Drive   │  ← Source documents## 🏗️ Architecture Overview## 🎯 Purpose

└────────┬────────┘

         │

         ▼

┌──────────────────────────────────────────────┐```This pipeline is designed to **ingest and prepare documents** for AI-powered knowledge retrieval systems. It handles the complete workflow from Google Drive to OpenAI Vector Stores, making your documents searchable via semantic AI.

│  INGEST SERVICE (services/ingest/)           │

│  • Syncs from Google Drive to S3             │┌─────────────────┐

│  • Processes with Unstructured.io            │

│  • Indexes to OpenAI Vector Store            ││  Google Drive   │**Note**: This repository handles **ingestion only**. For querying the vector store and building Custom GPT APIs, see the **[api-reference/](api-reference/)** folder.

│  • SQLite state tracking                     │

└────────┬─────────────────────────────────────┘│  (Source docs)  │

         │

         ▼└────────┬────────┘## � Repository Organization

┌──────────────────────────────────────────────┐

│  POSTGRES DATABASE                            │         │

│  • File metadata and state tracking          │

│  • Shared between services                   │         ▼This repository is organized into **two clear sections**:

└────────┬─────────────────────────────────────┘

         │┌──────────────────────────────────────────────┐

         ▼

┌──────────────────────────────────────────────┐│  INGEST SERVICE (services/ingest/)           │### 🔧 Root Directory (Ingestion Pipeline)

│  API SERVICE (services/api/)                 │

│  • FastAPI REST endpoints                    ││  ─────────────────────────────────────────   │**Purpose**: Sync documents from Google Drive to OpenAI Vector Stores

│  • Semantic search over Vector Store         │

│  • Metadata enrichment (Drive/S3 URLs)       ││  • Syncs from Google Drive to S3             │

│  • CORS support                              │

└──────────────────────────────────────────────┘│  • Processes with Unstructured.io            │**Key files**:

```

│  • Indexes to OpenAI Vector Store            │- `main.py` - Pipeline entry point

## 📁 Repository Structure

│  • Updates PostgreSQL & SQLite               │- `src/` - Pipeline source code (drive_sync, processor, indexer)

```

ai-knowledge-base-ingest/└────────┬─────────────────────────────────────┘- `data/pipeline.db` - SQLite database tracking file state

├── docker-compose.yml       # Orchestrates all services

├── Makefile                 # Helper commands         │

├── .env                     # Shared configuration

├── services/         ▼**Use this for**: Setting up and running the document ingestion workflow

│   ├── ingest/             # Ingestion service

│   │   ├── Dockerfile┌──────────────────────────────────────────────┐

│   │   ├── pyproject.toml

│   │   ├── uv.lock│  POSTGRES DATABASE                            │### 🚀 api-reference/ Folder (Query API Reference)

│   │   ├── main.py

│   │   ├── purge.py│  ─────────────────────────────────────────   │**Purpose**: Sample implementation for querying the vector store (for your future Custom GPT API)

│   │   └── src/            # Pipeline modules

│   └── api/                # API service│  • File metadata and state tracking          │

│       ├── Dockerfile

│       ├── pyproject.toml│  • Shared between ingest and API             │**Key files**:

│       ├── uv.lock

│       └── main.py└────────┬─────────────────────────────────────┘- `direct_search.py` - Search implementation (NO LLM required)

├── api-reference/          # Query API documentation & samples

└── test/                   # Test files and documentation         │- `README.md` - Complete API integration guide

```

         ▼- `QUICK_START.md` - 5-minute setup guide

## 🚀 Quick Start

┌──────────────────────────────────────────────┐- Performance benchmarks and accuracy reports

### Prerequisites

│  API SERVICE (services/api/)                 │

- Docker & Docker Compose

- Google Cloud service account JSON file│  ─────────────────────────────────────────   │**Use this for**: Building your Custom GPT API, implementing semantic search

- S3 credentials (AWS or DigitalOcean Spaces)

- OpenAI API key with Vector Store access│  • FastAPI REST endpoints                    │



### 1. Configure Environment│  • Semantic search over Vector Store         │### 📚 Quick Links



```bash│  • Metadata enrichment (Drive/S3 URLs)       │

# Copy example env file

cp .env.example .env│  • CORS support for web clients              │- **[api-reference/QUICK_START.md](api-reference/QUICK_START.md)** - 5-minute API setup



# Edit with your credentials└──────────────────────────────────────────────┘- **[api-reference/README.md](api-reference/README.md)** - Complete API guide

nano .env

``````



Required environment variables:## 🏗️ Architecture

```env

# Google Drive## 📁 Repository Structure

GOOGLE_SERVICE_ACCOUNT_FILE=./somer-services-458421-ee757e0c4238.json

GOOGLE_DRIVE_FOLDER_ID=your-folder-id```



# S3 Storage```┌─────────────────┐

S3_ENDPOINT=https://your-s3-endpoint.com

S3_ACCESS_KEY=your-access-keyai-knowledge-base-ingest/│  Google Drive   │

S3_SECRET_KEY=your-secret-key

S3_BUCKET=your-bucket-name├── docker-compose.yml       # Orchestrates all services│  (Source docs)  │

S3_REGION=us-east-1

├── .env                     # Shared configuration└────────┬────────┘

# OpenAI

OPENAI_API_KEY=sk-proj-...├── services/         │

VECTOR_STORE_ID=vs_...

│   ├── ingest/             # Ingestion service         ▼

# PostgreSQL

POSTGRES_DB=ai_knowledge_base│   │   ├── Dockerfile┌─────────────────────────────────────────┐

POSTGRES_USER=postgres

POSTGRES_PASSWORD=your-secure-password│   │   ├── pyproject.toml│  1. SYNC (drive_sync.py)                │



# API│   │   ├── main.py│     - List changed files                │

API_PORT=8000

```│   │   ├── purge.py│     - Download from Drive               │



### 2. Start Services│   │   └── src/            # Pipeline modules│     - Upload to S3                      │



```bash│   │       ├── config.py│     - Store metadata in SQLite          │

# Start all services

docker-compose up -d│   │       ├── database.py└────────┬────────────────────────────────┘



# Or use Makefile│   │       ├── drive_sync.py         │

make up

│   │       ├── processor.py         ▼

# Check status

docker-compose ps│   │       ├── indexer.py┌─────────────────────────────────────────┐

```

│   │       └── utils.py│  2. PROCESS (processor.py)              │

Services will be available at:

- **API**: http://localhost:8000│   └── api/                # API service│     - Fetch from S3                     │

- **API Docs**: http://localhost:8000/docs

- **PostgreSQL**: localhost:5432│       ├── Dockerfile│     - Process with Unstructured.io      │



### 3. Run Ingestion│       ├── pyproject.toml│     - Extract text, tables, images      │



```bash│       ├── main.py         # FastAPI app│     - Save structured data to S3        │

# Sync files from Google Drive

make ingest-sync│       └── README.md└────────┬────────────────────────────────┘

# or

docker-compose run --rm ingest python main.py sync --max-files 10├── data/                   # Shared volume (SQLite)         │



# Full pipeline (sync + process + index)│   └── pipeline.db         ▼

make ingest-full

# or└── README.md              # This file┌─────────────────────────────────────────┐

docker-compose run --rm ingest python main.py full --max-files 10

```│  3. INDEX (indexer.py)                  │

# Show statistics

make ingest-stats│     - Upload to OpenAI                  │

```

## 🚀 Quick Start│     - Add to Vector Store               │

### 4. Test API

│     - Enable semantic search            │

```bash

# Check health### Prerequisites└────────┬────────────────────────────────┘

curl http://localhost:8000/health

         │

# Perform search

curl -X POST http://localhost:8000/api/search \- Docker & Docker Compose         ▼

  -H "Content-Type: application/json" \

  -d '{"query": "Your question here", "max_results": 5}'- Google Cloud service account JSON file┌─────────────────┐



# Or use GET- S3 credentials (AWS or DigitalOcean Spaces)│  OpenAI Vector  │

curl "http://localhost:8000/api/search?q=Your+question&max_results=5"

- OpenAI API key with Vector Store access│     Store       │

# Interactive docs

open http://localhost:8000/docs│  (Searchable)   │

```

### 1. Configure Environment└─────────────────┘

## 🎯 Service Details

```

### Ingest Service

```bash

**Purpose**: Batch processing of documents from Drive to Vector Store

# Copy example env file## 🚀 Quick Start

**Technology**:

- Python 3.11cp .env.example .env

- uv for dependency management

- Isolated virtual environment### Prerequisites

- 150 packages (optimized)

# Edit with your credentials

**Key Dependencies**:

- `boto3` - S3 storagenano .env- Python 3.11+

- `google-api-python-client` - Google Drive API

- `openai` - Vector Store indexing```- Google Cloud service account with Drive API access

- `unstructured` - Document processing

- `tqdm` - Progress tracking- AWS S3 bucket



**Commands**:Required environment variables:- OpenAI API key with Vector Store access

```bash

# Sync from Drive```env- Unstructured.io API key (optional, for cloud processing)

docker-compose run --rm ingest python main.py sync --max-files 10

# Google Drive

# Process files

docker-compose run --rm ingest python main.py process --max-files 10GOOGLE_SERVICE_ACCOUNT_FILE=./somer-services-458421-ee757e0c4238.json### Installation



# Index to Vector StoreGOOGLE_DRIVE_FOLDER_ID=your-folder-id

docker-compose run --rm ingest python main.py index --max-files 10

```bash

# Full pipeline

docker-compose run --rm ingest python main.py full --max-files 10# S3 Storage# Clone the repository



# StatisticsS3_ENDPOINT=https://your-s3-endpoint.comgit clone <your-repo-url>

docker-compose run --rm ingest python main.py stats

S3_ACCESS_KEY=your-access-keycd ai-knowledge-base-ingest

# Cleanup stale files

docker-compose run --rm ingest python main.py cleanupS3_SECRET_KEY=your-secret-key

```

S3_BUCKET=your-bucket-name# Install dependencies with uv (recommended)

### API Service

S3_REGION=us-east-1uv sync

**Purpose**: REST API for semantic search



**Technology**:

- Python 3.11# OpenAI# Or with pip

- FastAPI framework

- uv for dependency managementOPENAI_API_KEY=sk-proj-...pip install -e .

- Isolated virtual environment

- 32 packages (minimal!)VECTOR_STORE_ID=vs_...```



**Key Dependencies**:

- `fastapi` - Web framework

- `uvicorn` - ASGI server# PostgreSQL### Configuration

- `httpx` - HTTP client

- `boto3` - S3 presigned URLsPOSTGRES_DB=ai_knowledge_base

- `python-dotenv` - Configuration

POSTGRES_USER=postgres1. Copy the example environment file:

**Endpoints**:

- `GET /` - Service informationPOSTGRES_PASSWORD=your-secure-password```bash

- `GET /health` - Health check

- `POST /api/search` - Semantic search (JSON body)cp .env.example .env

- `GET /api/search` - Semantic search (URL params)

- `GET /docs` - Interactive API docs (Swagger UI)# API```



**Features**:API_PORT=8000

- Automatic metadata enrichment

- Drive URLs and S3 presigned URLs```2. Edit `.env` with your credentials:

- CORS support

- Health checks```env

- OpenAPI/Swagger documentation

### 2. Start Services# Google Drive

### PostgreSQL Database

GOOGLE_CREDENTIALS_FILE=path/to/service-account.json

**Purpose**: Shared metadata storage

```bashDRIVE_FOLDER_ID=your-drive-folder-id

**Technology**:

- PostgreSQL 16 Alpine# Start all services

- Persistent volumes

- Health checksdocker-compose up -d# AWS S3

- Automatic initialization

AWS_ACCESS_KEY_ID=your-access-key

**Schema**:

```sql# Check statusAWS_SECRET_ACCESS_KEY=your-secret-key

-- File state tracking

CREATE TABLE file_state (docker-compose psAWS_REGION=us-east-1

    id SERIAL PRIMARY KEY,

    sha256 VARCHAR(64) UNIQUE NOT NULL,S3_BUCKET_NAME=your-bucket-name

    s3_key TEXT NOT NULL,

    original_name TEXT NOT NULL,# View logs

    status VARCHAR(20) NOT NULL,

    synced_at TIMESTAMP,docker-compose logs -f# OpenAI

    processed_at TIMESTAMP,

    indexed_at TIMESTAMP,```OPENAI_API_KEY=sk-proj-...

    openai_file_id TEXT,

    error_message TEXTVECTOR_STORE_ID=vs_...

);

Services will be available at:

-- Google Drive mapping

CREATE TABLE drive_file_mapping (- **API**: http://localhost:8000# Unstructured.io (optional)

    id SERIAL PRIMARY KEY,

    sha256 VARCHAR(64) NOT NULL,- **API Docs**: http://localhost:8000/docsUNSTRUCTURED_API_KEY=your-api-key

    drive_file_id VARCHAR(255) NOT NULL,

    drive_file_name TEXT NOT NULL,- **PostgreSQL**: localhost:5432UNSTRUCTURED_API_URL=https://api.unstructuredapp.io/general/v0/general

    drive_parent_path TEXT,

    drive_modified_time TIMESTAMP,```

    FOREIGN KEY (sha256) REFERENCES file_state(sha256)

);### 3. Run Ingestion

```

## 📖 Usage

## 🛠️ Development

```bash

### Local Development (Without Docker)

# Sync files from Google Drive### Basic Commands

**API Service:**

```bashdocker-compose run --rm ingest uv run python main.py sync --max-files 10

cd services/api

uv sync```bash

uv run uvicorn main:app --reload --port 8000

```# Process files with Unstructured.io# Full pipeline - sync, process, and index



**Ingest Service:**docker-compose run --rm ingest uv run python main.py process --max-files 10uv run python main.py

```bash

cd services/ingest

uv sync

uv run python main.py sync --max-files 5# Index to OpenAI Vector Store# Individual stages

```

docker-compose run --rm ingest uv run python main.py index --max-files 10uv run python main.py sync              # Sync from Drive to S3

### Building Images

uv run python main.py process           # Process files with Unstructured

```bash

# Build all services# Or run full pipelineuv run python main.py index             # Index files to OpenAI

docker-compose build

# ordocker-compose run --rm ingest uv run python main.py full --max-files 10

make build

```# Dry run (test without changes)

# Build specific service

docker-compose build apiuv run python main.py --dry-run sync

docker-compose build ingest

### 4. Test API

# Build with no cache

docker-compose build --no-cache# Limit number of files

```

```bashuv run python main.py --max-files 10 sync

### Makefile Commands

# Check health```

```bash

make help           # Show all commandscurl http://localhost:8000/health

make build          # Build all Docker images

make up             # Start all services### Pipeline Stages

make down           # Stop all services

make logs           # View logs from all services# Perform search

make restart        # Restart all services

make clean          # Remove all containers and volumescurl -X POST http://localhost:8000/api/search \#### 1. Sync Stage



# Ingestion  -H "Content-Type: application/json" \Syncs files from Google Drive to S3:

make ingest-sync    # Sync files from Drive

make ingest-process # Process files  -d '{"query": "What is Centropa?", "max_results": 5}'- Lists all files in the configured Drive folder (recursive)

make ingest-full    # Run full pipeline

make ingest-stats   # Show statistics- Detects changes using modification timestamps and SHA256 hashes



# API# Or use GET- Downloads changed files from Drive

make api-test       # Test API health

make api-search     # Example search querycurl "http://localhost:8000/api/search?q=Holocaust+education&max_results=5"- Uploads to S3 with metadata



# Development```- Exports Google Workspace files (Docs, Sheets, Slides) to Office formats

make dev-api        # Run API locally (no Docker)

make dev-ingest     # Run ingest locally (no Docker)- Stores file state in SQLite database

```

## 🐳 Docker Services

## 📊 Monitoring

```bash

### Check Service Status

### Ingest Serviceuv run python main.py sync --max-files 100

```bash

# All services```

docker-compose ps

**Purpose**: Sync, process, and index documents

# Logs (all services)

docker-compose logs -f#### 2. Process Stage



# Logs (specific service)**Volumes**:Processes files with Unstructured.io:

docker-compose logs -f api

docker-compose logs -f ingest- `shared_data:/app/data` - SQLite database (shared with API)- Fetches raw files from S3

docker-compose logs -f postgres

- Service account JSON (read-only)- Extracts text, tables, and images

# Resource usage

docker stats- Structures content into chunks

```

**Usage**:- Saves processed output back to S3

### Health Checks

```bash- Supports 30+ file formats (PDF, DOCX, PPTX, images, etc.)

```bash

# API health# One-time sync

curl http://localhost:8000/health

docker-compose run --rm ingest uv run python main.py sync```bash

# PostgreSQL health

docker-compose exec postgres pg_isreadyuv run python main.py process --max-files 50



# Check all services# Scheduled via cron (host machine)```

docker-compose ps

```0 */6 * * * cd /path/to/repo && docker-compose run --rm ingest uv run python main.py full



### Database Queries```#### 3. Index Stage



```bashIndexes processed files to OpenAI Vector Store:

# Connect to PostgreSQL

docker-compose exec postgres psql -U postgres -d ai_knowledge_base**Commands**:- Uploads processed text files to OpenAI



# Check file counts- `sync` - Sync from Google Drive to S3- Adds files to Vector Store

SELECT status, COUNT(*) FROM file_state GROUP BY status;

- `process` - Process files with Unstructured.io- Enables semantic search

# View recent files

SELECT original_name, status, synced_at - `index` - Index to OpenAI Vector Store- Updates database with OpenAI file IDs

FROM file_state 

ORDER BY synced_at DESC - `full` - Run complete pipeline

LIMIT 10;

- `stats` - Show pipeline statistics```bash

# Check for errors

SELECT original_name, error_message - `cleanup` - Clean stale filesuv run python main.py index --max-files 50

FROM file_state 

WHERE status LIKE 'failed%' ```

ORDER BY synced_at DESC;

```### API Service



## 🔒 Security Best Practices## 🗄️ Database Schema



1. **Never commit secrets****Purpose**: REST API for semantic search

   - Keep `.env` file local (in `.gitignore`)

   - Rotate API keys regularlyThe pipeline uses SQLite to track file state:

   - Use environment-specific configurations

**Ports**: `8000:8000` (configurable via `API_PORT`)

2. **Secure service account**

   - Limit Drive folder access```sql

   - Use least-privilege permissions

   - Store JSON file securely**Endpoints**:-- Main file tracking table



3. **Database security**- `GET /` - Service infoCREATE TABLE file_state (

   - Use strong PostgreSQL password

   - Don't expose port 5432 publicly- `GET /health` - Health check    id INTEGER PRIMARY KEY,

   - Regular backups

   - Enable SSL in production- `POST /api/search` - Semantic search (JSON)    sha256 TEXT UNIQUE NOT NULL,



4. **S3 bucket**- `GET /api/search` - Semantic search (query params)    s3_key TEXT NOT NULL,

   - Enable encryption at rest

   - Use presigned URLs (1 hour expiry)- `GET /docs` - Interactive API docs (Swagger UI)    original_name TEXT NOT NULL,

   - Restrict IAM policies

   - Enable versioning    mime_type TEXT,



5. **API security** (Production)**Features**:    size_bytes INTEGER,

   - Add authentication middleware

   - Enable HTTPS/TLS- FastAPI with automatic OpenAPI docs    status TEXT NOT NULL,

   - Configure CORS appropriately

   - Implement rate limiting- Metadata enrichment (Drive URLs, S3 presigned URLs)    synced_at TIMESTAMP,

   - Use API keys or JWT tokens

- CORS support    processed_at TIMESTAMP,

## 🐛 Troubleshooting

- Health checks    indexed_at TIMESTAMP,

### Services won't start

    openai_file_id TEXT,

```bash

# Check logs### PostgreSQL Service    error_message TEXT

docker-compose logs

);

# Rebuild images

docker-compose build --no-cache**Purpose**: Shared database for metadata

docker-compose up -d

```-- Google Drive file mapping



### API can't connect to database**Ports**: `5432:5432`CREATE TABLE drive_file_mapping (



```bash    id INTEGER PRIMARY KEY,

# Check PostgreSQL is running

docker-compose ps postgres**Volumes**: `postgres_data:/var/lib/postgresql/data`    sha256 TEXT NOT NULL,



# Test connectivity    drive_file_id TEXT NOT NULL,

docker-compose exec api ping postgres

## 📖 Usage Examples    drive_file_name TEXT NOT NULL,

# Verify environment variables

docker-compose exec api env | grep POSTGRES    drive_parent_path TEXT,

```

### Running Ingestion    drive_modified_time TIMESTAMP,

### Ingest can't access service account

    FOREIGN KEY (sha256) REFERENCES file_state(sha256)

```bash

# Check file exists```bash);

ls -la somer-services-458421-ee757e0c4238.json

# Dry run (test without changes)```

# Verify mount in container

docker-compose run --rm ingest ls -la /app/service-account.jsondocker-compose run --rm ingest uv run python main.py --dry-run sync

```

## 📁 Project Structure

### Port conflicts

# Sync limited files

```bash

# Change ports in .envdocker-compose run --rm ingest uv run python main.py sync --max-files 10```

API_PORT=8001

POSTGRES_PORT=5433ai-knowledge-base-ingest/



# Restart services# Full pipeline with limits├── main.py                  # Main entry point

docker-compose down

docker-compose up -ddocker-compose run --rm ingest uv run python main.py full --max-files 50├── purge.py                 # Cleanup utility

```

├── pyproject.toml           # Dependencies

### Dependencies not updating

# Show statistics├── docker-compose.yml       # Docker setup

```bash

# Rebuild without cachedocker-compose run --rm ingest uv run python main.py stats├── Dockerfile               # Container definition

cd services/ingest  # or services/api

uv lock --upgrade├── .env                     # Configuration (not in git)

cd ../..

docker-compose build --no-cache ingest  # or api# Cleanup stale files├── .env.example             # Configuration template

```

docker-compose run --rm ingest uv run python main.py cleanup├── data/                    # Database and temp files

## 🏗️ Isolated Python Environments

```│   └── pipeline.db          # SQLite database

Each service has its own **isolated Python virtual environment** managed by uv:

├── src/                     # Source code

### Benefits

### Using the API│   ├── config.py            # Configuration management

✅ **Dependency isolation** - API and ingest dependencies don't conflict  

✅ **Reproducible builds** - Each service has exact versions via `uv.lock`  │   ├── database.py          # Database operations

✅ **Better layer caching** - Dependencies cached separately from code  

✅ **Faster rebuilds** - Only affected service rebuilds  **Python:**│   ├── drive_sync.py        # Google Drive sync

✅ **Smaller images** - Using official uv binary

```python│   ├── processor.py         # Unstructured.io processing

### How It Works

import httpx│   ├── indexer.py           # OpenAI indexing

**Dockerfiles use:**

```dockerfile│   └── utils.py             # Shared utilities

# Official uv image (efficient)

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uvresponse = httpx.post(└── api-reference/           # API reference for querying



# Isolated venv    "http://localhost:8000/api/search",    ├── README.md            # API documentation

ENV UV_PROJECT_ENVIRONMENT=/app/.venv

ENV PATH="/app/.venv/bin:$PATH"    json={"query": "Holocaust education", "max_results": 10}    ├── direct_search.py     # Vector store search sample



# Install dependencies)    └── *.md                 # Analysis and benchmarks

RUN uv venv /app/.venv

RUN uv sync --frozen --no-devresults = response.json()```



# Direct execution (no wrapper overhead)

CMD ["/app/.venv/bin/python", "main.py"]

```for result in results["results"]:## 🔧 Advanced Usage



### Dependency Management    print(f"File: {result['metadata']['original_name']}")



**Adding dependencies:**    print(f"Score: {result['score']}")### Dry Run Mode

```bash

cd services/api  # or services/ingest    print(f"Drive URL: {result['metadata']['drive_url']}")

uv add httpx

uv lock    print()Test the pipeline without making changes:

```

``````bash

**Updating dependencies:**

```bashuv run python main.py --dry-run sync

cd services/api  # or services/ingest

uv lock --upgrade**JavaScript:**uv run python main.py --dry-run process

docker-compose build api  # or ingest

``````javascript```



**Checking versions:**const response = await fetch('http://localhost:8000/api/search', {

```bash

cd services/api  # or services/ingest  method: 'POST',### Limit Files

uv tree

```  headers: {'Content-Type': 'application/json'},



## 📦 Version Control  body: JSON.stringify({Process only a subset of files:



### What to Commit    query: 'Holocaust education',```bash



✅ **Safe to commit:**    max_results: 10uv run python main.py --max-files 5 sync

- Source code (`services/*/main.py`, `services/*/src/`)

- Dockerfiles  })uv run python main.py --max-files 10 process

- `docker-compose.yml`

- `pyproject.toml` and `uv.lock` files});```

- Configuration templates (`.env.example`)

- Documentation



❌ **Never commit:**const data = await response.json();### Verbose Logging

- `.env` file (contains secrets)

- Service account JSON files (`*.json`)console.log(`Found ${data.count} results`);

- Database files (`*.db`)

- Virtual environments (`.venv/`)```Enable detailed debug output:

- Backup files (`*.old`, `*.backup`)

```bash

### .gitignore

**cURL:**uv run python main.py --verbose sync

The repository includes comprehensive `.gitignore` for:

- Python artifacts (`__pycache__`, `*.pyc`)```bash```

- Virtual environments (`.venv/`)

- Environment files (`.env`)curl -X POST http://localhost:8000/api/search \

- Database files (`*.db`)

- Backup files (`*.old`, `*.backup`)  -H "Content-Type: application/json" \### Purge Data

- OS files (`.DS_Store`)

- Docker volumes  -d '{



## 🎓 What's Next?    "query": "What is Centropa?",Clean up all data (⚠️ destructive):



### For Ingestion Setup    "max_results": 5,```bash



1. ✅ Configure `.env` with your credentials    "rewrite_query": true# Dry run to see what would be deleted

2. ✅ Start services: `make up`

3. ✅ Run ingestion: `make ingest-sync`  }'uv run python purge.py --dry-run

4. ✅ Monitor logs: `make logs`

```

### For API Development

# Delete everything (requires confirmation)

1. ✅ Check API health: `make api-test`

2. ✅ Visit interactive docs: http://localhost:8000/docs### Managing Servicesuv run python purge.py

3. ✅ Test search: `curl "http://localhost:8000/api/search?q=test"`

4. ✅ Review `api-reference/` for advanced examples



### Production Deployment```bash# Delete everything without confirmation (dangerous!)



1. ✅ Set up managed PostgreSQL# Start servicesuv run python purge.py --yes

2. ✅ Configure HTTPS/TLS for API

3. ✅ Add authentication middlewaredocker-compose up -d```

4. ✅ Set up monitoring (Prometheus, Grafana)

5. ✅ Configure automated backups

6. ✅ Schedule ingestion with cron

7. ✅ Enable rate limiting# Stop servicesOptions:



## 📚 Additional Resourcesdocker-compose down- `--dry-run` - Show what would be deleted without making changes



- **api-reference/** - Complete query API documentation and samples- `--s3-only` - Delete only S3 bucket contents

- **test/** - Test files and Custom GPT documentation

- **Makefile** - Run `make help` for all commands# Rebuild after code changes- `--db-only` - Delete only database file

- **API Docs** - http://localhost:8000/docs (when running)

docker-compose build- `--vector-store-only` - Delete only Vector Store files

## 🤝 Contributing

- `--yes` - Skip confirmation prompt

1. Make changes in appropriate service directory

2. Test locally with `docker-compose up`# View logs

3. Update documentation if needed

4. Commit with clear messagesdocker-compose logs -f api## 🐳 Docker Deployment



## 📝 Licensedocker-compose logs -f ingest



Internal use only.### Using Docker Compose



---# Restart specific service



**Ready to start?**docker-compose restart api```bash



```bash# Build and run

# 1. Configure

cp .env.example .env# Remove everything (including volumes)docker-compose up -d

nano .env

docker-compose down -v

# 2. Start everything

make up```# View logs



# 3. Run ingestiondocker-compose logs -f

make ingest-sync

## 🔧 Development

# 4. Test API

curl http://localhost:8000/health# Stop



# 5. Interactive docs### Local Development (Without Docker)docker-compose down

open http://localhost:8000/docs

``````



🚀 **Your AI Knowledge Base is ready!****API Service:**


```bash### Using Docker Directly

cd services/api

uv sync```bash

uv run uvicorn main:app --reload --port 8000# Build image

```docker build -t knowledge-ingest .



**Ingest Service:**# Run container

```bashdocker run -d \

cd services/ingest  --name knowledge-ingest \

uv sync  --env-file .env \

uv run python main.py sync --max-files 5  -v $(pwd)/data:/app/data \

```  knowledge-ingest

```

### Building Images

## 📊 Monitoring

```bash

# Build all servicesThe pipeline provides detailed progress tracking:

docker-compose build

```

# Build specific serviceSyncing from Google Drive...

docker-compose build api━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00

docker-compose build ingest✓ Successfully synced 10 files



# Build with no cacheProcessing with Unstructured.io...

docker-compose build --no-cache━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:30

```✓ Successfully processed 10 files



## 🔒 SecurityIndexing to OpenAI Vector Store...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:01:00

### Best Practices✓ Successfully indexed 10 files

```

1. **Never commit secrets**

   - Add `.env` to `.gitignore`Check database for file status:

   - Use environment variables```bash

   - Rotate API keys regularlysqlite3 data/pipeline.db "SELECT status, COUNT(*) FROM file_state GROUP BY status"

```

2. **Secure service account**

   - Limit Drive folder access## 🔍 Supported File Types

   - Use read-only when possible

   - Store JSON file securelyThe pipeline supports 30+ file formats:



3. **Database security****Documents**: PDF, DOCX, DOC, ODT, RTF, TXT, MD  

   - Use strong PostgreSQL password**Spreadsheets**: XLSX, XLS, CSV, ODS  

   - Don't expose port 5432 publicly**Presentations**: PPTX, PPT, ODP  

   - Regular backups**Images**: JPG, PNG, TIFF (with OCR)  

**Google Workspace**: Docs, Sheets, Slides (auto-converted)  

4. **S3 bucket****Archives**: ZIP (auto-extracted)  

   - Enable encryption at rest**Email**: EML, MSG  

   - Use presigned URLs (1 hour expiry)

   - Restrict IAM policies## 🚦 File Processing States



5. **API security**Files move through these states:

   - Add authentication middleware for production

   - Enable HTTPS1. **synced** - Downloaded from Drive, uploaded to S3

   - Configure CORS appropriately2. **processed** - Processed by Unstructured.io

   - Rate limiting3. **indexed** - Indexed in OpenAI Vector Store

4. **error** - Processing failed (check error_message)

## 🐛 Troubleshooting

## 🔗 Integration with Custom GPT API

### Common Issues

After ingestion, documents are searchable via OpenAI Vector Stores. See the `api-reference/` folder for:

**Services won't start:**

```bash- **direct_search.py** - Sample implementation for semantic search

# Check logs- **README.md** - Complete API integration guide

docker-compose logs- Performance benchmarks and test results

- Code samples for FastAPI, Flask, Express

# Rebuild images

docker-compose build --no-cacheThe API reference shows how to:

docker-compose up -d- Query the vector store without using an LLM (5x faster, cheaper)

```- Enrich results with Drive URLs and S3 presigned URLs

- Build Custom GPT actions

**API can't connect to database:**- Handle multilingual content

```bash

# Check PostgreSQL is running## 🐛 Troubleshooting

docker-compose ps postgres

### Common Issues

# Verify environment variables

docker-compose exec api env | grep POSTGRES**Google Drive authentication fails**

``````bash

# Check service account file exists

**Ingest can't access service account:**ls -la your-service-account.json

```bash

# Check file exists# Verify Drive API is enabled

ls -la somer-services-458421-ee757e0c4238.json# Check permissions in Google Cloud Console

```

# Verify mount in container

docker-compose run --rm ingest ls -la /app/service-account.json**S3 upload fails**

``````bash

# Test AWS credentials

**Database connection refused:**aws s3 ls s3://your-bucket-name/

```bash

# Check PostgreSQL health# Check IAM permissions (s3:PutObject, s3:GetObject)

docker-compose exec postgres pg_isready```



# Check network**OpenAI indexing fails**

docker-compose exec api ping postgres```bash

```# Verify API key

curl -H "Authorization: Bearer $OPENAI_API_KEY" \

## 📈 Performance  https://api.openai.com/v1/models



### Scaling# Check vector store exists

# Verify API key has vector store access

**API Service:**```

```yaml

services:**Processing fails**

  api:```bash

    deploy:# Check Unstructured.io API key

      replicas: 3curl -H "unstructured-api-key: $UNSTRUCTURED_API_KEY" \

```  https://api.unstructuredapp.io/general/v0/general



**Database:**# Try processing locally (no API key needed)

- Use managed PostgreSQL for production# Set UNSTRUCTURED_API_KEY="" in .env

- Configure connection pooling```

- Add read replicas if needed

### Debug Mode

**Ingest:**

- Run on schedule (cron)Enable detailed logging:

- Adjust `--max-files` based on resources```bash

- Use `--processor-workers` for parallel processinguv run python main.py --verbose sync 2>&1 | tee debug.log

```

## 🎯 Next Steps

Check database state:

1. **Configure**: Edit `.env` with your credentials```bash

2. **Start**: Run `docker-compose up -d`sqlite3 data/pipeline.db

3. **Ingest**: Run `docker-compose run --rm ingest uv run python main.py sync`

4. **Test**: Visit http://localhost:8000/docs# List all tables

5. **Query**: Use API to search your knowledge base.tables



**Ready to build something amazing! 🚀**# Check file states

SELECT status, COUNT(*) FROM file_state GROUP BY status;

# View recent errors
SELECT original_name, error_message, synced_at 
FROM file_state 
WHERE status = 'error' 
ORDER BY synced_at DESC 
LIMIT 10;
```

## 📈 Performance

Typical processing times:
- **Sync**: ~1-2 seconds per file (depends on Drive API)
- **Process**: ~5-10 seconds per file (depends on Unstructured.io)
- **Index**: ~2-3 seconds per file (depends on OpenAI API)

Batch recommendations:
- Start with `--max-files 10` to test
- Scale up to `--max-files 100` for production
- Use `--dry-run` to preview changes

## 🔒 Security

- Keep `.env` file secure (never commit to git)
- Use least-privilege IAM policies for S3
- Rotate API keys regularly
- Use service accounts for Google Drive (not personal accounts)
- Limit Drive folder access to only necessary files
- Enable S3 bucket encryption
- Use presigned URLs with short expiration (1 hour)

## 🤝 Contributing

This is an internal tool, but improvements are welcome:

1. Test changes thoroughly with `--dry-run`
2. Update documentation
3. Check error handling
4. Verify database migrations

## 📝 License

Internal use only.

## 🆘 Support

For issues with:
- **Ingestion pipeline**: Check this README and troubleshooting section
- **API integration**: See `api-reference/README.md`
- **Custom GPT setup**: Refer to API reference documentation

---

## 🔄 Workflow Overview

```
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: INGEST (Root Directory)                           │
│  ─────────────────────────────────────────────────────────  │
│  Run: uv run python main.py                                 │
│                                                              │
│  1. Sync from Google Drive to S3                            │
│  2. Process with Unstructured.io                            │
│  3. Index to OpenAI Vector Store                            │
│                                                              │
│  Result: Documents searchable in vector store               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: BUILD API (api-reference/)                        │
│  ─────────────────────────────────────────────────────────  │
│  Reference: api-reference/README.md                         │
│  Sample: api-reference/direct_search.py                     │
│                                                              │
│  1. Copy direct_search.py to your API project              │
│  2. Implement HTTP endpoint (FastAPI/Flask/Express)        │
│  3. Deploy your API                                         │
│  4. Connect Custom GPT                                      │
│                                                              │
│  Result: Custom GPT can query your knowledge base          │
└─────────────────────────────────────────────────────────────┘
```

**Ingestion**: Keeps vector store up-to-date with latest documents (run periodically)  
**API**: Queries vector store on-demand for Custom GPT (always-on service)

---

## 📦 Version Control

### What to Commit

✅ **Safe to commit**:
- All source code (`main.py`, `src/`, `api-reference/`)
- Documentation files (`.md`)
- Configuration templates (`.env.example`)
- Docker files (`Dockerfile`, `docker-compose.yml`)
- Dependencies (`pyproject.toml`, `uv.lock`)

⚠️ **Check .gitignore before committing**:
- `.env` (should be ignored - contains secrets)
- `data/pipeline.db` (may contain sensitive file metadata)
- `*.json` (service account credentials)

❌ **Never commit**:
- `.env` file with credentials
- Service account JSON files
- Database with production data
- API keys or secrets

### Suggested Commit Message

```bash
git add -A
git commit -m "refactor: Separate ingestion pipeline from API reference

Reorganized repository for clear separation of concerns:

ADDED:
- Comprehensive documentation for ingestion and API
- api-reference/ folder with complete integration guide
- Enhanced direct_search.py with --full and --preview-length options

REMOVED FROM ROOT:
- Query tools and documentation (moved to api-reference/)

BENEFITS:
- Clear separation: ingestion vs API development
- Better documentation structure
- Ready for Custom GPT API integration"

git push origin main
```

---

## 🎓 Next Steps

### For Ingestion Setup
1. ✅ Read this README
2. ✅ Configure `.env` with your credentials
3. ✅ Run `uv run python main.py --dry-run sync` to test
4. ✅ Run full pipeline: `uv run python main.py`

### For API Development
1. ✅ Go to `api-reference/` folder
2. ✅ Read `QUICK_START.md` (5 minutes)
3. ✅ Test: `uv run python api-reference/direct_search.py "test query"`
4. ✅ Review code samples in `README.md`
5. ✅ Copy to your API project and deploy

---

**Ready to start?**
1. Configure `.env` with your credentials
2. Run `uv run python main.py --dry-run sync` to test
3. Process files with `uv run python main.py`
4. Build your API using `api-reference/` as a guide
