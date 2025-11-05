# AI Knowledge Base Ingest Pipeline# AI Knowledge Base Ingest Pipeline



A robust document ingestion pipeline that syncs documents from Google Drive, processes them with Unstructured.io or IBM Docling, stores them in S3, and indexes them in OpenAI Vector Stores for semantic search.A robust document ingestion pipeline that syncs documents from Google Drive, processes them with Unstructured.io or IBM Docling, stores them in S3, and indexes them in OpenAI Vector Stores for semantic search.



## 🏗️ Architecture



```## 🏗️ ArchitectureA modular document ingestion and search system with separate Docker services for ingestion, API, and database.A robust document ingestion pipeline that syncs documents from Google Drive, processes them with Unstructured.io, stores them in S3, and indexes them in OpenAI Vector Stores for semantic search.

┌─────────────────┐

│  Google Drive   │  ← Source documents

└────────┬────────┘

         │```

         ▼

┌──────────────────────────────────────────────┐┌─────────────────┐

│  INGEST SERVICE (services/ingest/)           │

│  • Syncs from Google Drive to S3             ││  Google Drive   │  ← Source documents## 🏗️ Architecture Overview## 🎯 Purpose

│  • Processes with Unstructured/Docling       │

│  • Indexes to OpenAI Vector Store            │└────────┬────────┘

│  • PostgreSQL state tracking                 │

└────────┬─────────────────────────────────────┘         │

         │

         ▼         ▼

┌──────────────────────────────────────────────┐

│  POSTGRES DATABASE                            │┌──────────────────────────────────────────────┐```This pipeline is designed to **ingest and prepare documents** for AI-powered knowledge retrieval systems. It handles the complete workflow from Google Drive to OpenAI Vector Stores, making your documents searchable via semantic AI.

│  • File metadata and state tracking          │

│  • Shared between services                   ││  INGEST SERVICE (services/ingest/)           │

└────────┬─────────────────────────────────────┘

         ││  • Syncs from Google Drive to S3             │┌─────────────────┐

         ▼

┌──────────────────────────────────────────────┐│  • Processes with Unstructured.io            │

│  API SERVICE (services/api/)                 │

│  • FastAPI REST endpoints                    ││  • Indexes to OpenAI Vector Store            ││  Google Drive   │**Note**: This repository handles **ingestion only**. For querying the vector store and building Custom GPT APIs, see the **[api-reference/](api-reference/)** folder.

│  • Semantic search over Vector Store         │

│  • Metadata enrichment (Drive/S3 URLs)       ││  • SQLite state tracking                     │

│  • CORS support                              │

└──────────────────────────────────────────────┘└────────┬─────────────────────────────────────┘│  (Source docs)  │

```

         │

## 📁 Repository Structure

         ▼└────────┬────────┘## � Repository Organization

```

ai-knowledge-base-ingest/┌──────────────────────────────────────────────┐

├── docker-compose.yml       # Orchestrates all services

├── Makefile                 # Helper commands│  POSTGRES DATABASE                            │         │

├── .env                     # Configuration (not in git)

├── services/│  • File metadata and state tracking          │

│   ├── ingest/             # Ingestion service

│   │   ├── Dockerfile│  • Shared between services                   │         ▼This repository is organized into **two clear sections**:

│   │   ├── pyproject.toml

│   │   ├── main.py└────────┬─────────────────────────────────────┘

│   │   ├── purge.py

│   │   └── src/            # Pipeline modules         │┌──────────────────────────────────────────────┐

│   └── api/                # API service

│       ├── Dockerfile         ▼

│       ├── pyproject.toml

│       └── main.py┌──────────────────────────────────────────────┐│  INGEST SERVICE (services/ingest/)           │### 🔧 Root Directory (Ingestion Pipeline)

├── api-reference/          # Query API documentation & samples

└── test/                   # Test files and documentation│  API SERVICE (services/api/)                 │

```

│  • FastAPI REST endpoints                    ││  ─────────────────────────────────────────   │**Purpose**: Sync documents from Google Drive to OpenAI Vector Stores

## 🚀 Quick Start

│  • Semantic search over Vector Store         │

### Prerequisites

│  • Metadata enrichment (Drive/S3 URLs)       ││  • Syncs from Google Drive to S3             │

- Docker & Docker Compose

- Google Cloud service account JSON file│  • CORS support                              │

- S3 credentials (AWS or DigitalOcean Spaces)

- OpenAI API key with Vector Store access└──────────────────────────────────────────────┘│  • Processes with Unstructured.io            │**Key files**:



### 1. Configure Environment```



```bash│  • Indexes to OpenAI Vector Store            │- `main.py` - Pipeline entry point

# Copy example env file

cp .env.example .env## 📁 Repository Structure



# Edit with your credentials│  • Updates PostgreSQL & SQLite               │- `src/` - Pipeline source code (drive_sync, processor, indexer)

nano .env

``````



Required environment variables:ai-knowledge-base-ingest/└────────┬─────────────────────────────────────┘- `data/pipeline.db` - SQLite database tracking file state



```env├── docker-compose.yml       # Orchestrates all services

# Google Drive

GOOGLE_SERVICE_ACCOUNT_FILE=./google-service-account.json

GOOGLE_DRIVE_FOLDER_ID=your-folder-id

├── .env                     # Shared configuration

# S3 Storage

S3_ENDPOINT=https://your-s3-endpoint.com├── services/         ▼**Use this for**: Setting up and running the document ingestion workflow

S3_ACCESS_KEY=your-access-key

S3_SECRET_KEY=your-secret-key│   ├── ingest/             # Ingestion service

S3_BUCKET=your-bucket-name

S3_REGION=us-east-1│   │   ├── Dockerfile┌──────────────────────────────────────────────┐



# OpenAI│   │   ├── pyproject.toml

OPENAI_API_KEY=sk-proj-...

VECTOR_STORE_ID=vs_...│   │   ├── uv.lock│  POSTGRES DATABASE                            │### 🚀 api-reference/ Folder (Query API Reference)



# PostgreSQL│   │   ├── main.py

POSTGRES_DB=ai_knowledge_base

POSTGRES_USER=postgres│   │   ├── purge.py│  ─────────────────────────────────────────   │**Purpose**: Sample implementation for querying the vector store (for your future Custom GPT API)

POSTGRES_PASSWORD=your-secure-password

│   │   └── src/            # Pipeline modules

# Processing Engine (optional)

PROCESSING_ENGINE=unstructured  # or "docling"│   └── api/                # API service│  • File metadata and state tracking          │



# API│       ├── Dockerfile

API_PORT=8000

```│       ├── pyproject.toml│  • Shared between ingest and API             │**Key files**:



### 2. Start Services│       ├── uv.lock



```bash│       └── main.py└────────┬─────────────────────────────────────┘- `direct_search.py` - Search implementation (NO LLM required)

# Start all services

docker-compose up -d├── api-reference/          # Query API documentation & samples



# Or use Makefile└── test/                   # Test files and documentation         │- `README.md` - Complete API integration guide

make up

```

# Check status

docker-compose ps         ▼- `QUICK_START.md` - 5-minute setup guide

```

## � Docker Images

This project provides multiple Docker Compose configurations for different deployment scenarios:

### 📁 Available Compose Files
- `docker-compose.yml` - **Default**: Local builds (development/testing)
- `docker-compose-from-registry.yml` - **Production**: Pre-built images from GitHub Container Registry
- `docker-compose-local-builld.yml` - **Explicit**: Local builds (same as default)

### 🏭 Production Deployment (Recommended)
Uses pre-built images from GitHub Container Registry, with optional Cloudflare Tunnel integration:
```bash
# Local access only
docker-compose -f docker-compose-from-registry.yml up -d

# With Cloudflare Tunnel (external access)
docker-compose -f docker-compose-from-registry.yml --profile tunnel up -d
```

> 🔧 **CI Optimization**: Images are built only when relevant code changes. See [CI_OPTIMIZATION_GUIDE.md](./CI_OPTIMIZATION_GUIDE.md)  
> 🌐 **Cloudflare Tunnel**: Secure external access without port forwarding. See [CLOUDFLARE_TUNNEL_SETUP.md](./CLOUDFLARE_TUNNEL_SETUP.md)

**Available Images:**
- `ghcr.io/hasomerhacairhu/ai-knowledge-base/api:latest` - REST API service
- `ghcr.io/hasomerhacairhu/ai-knowledge-base/ingest:latest` - Document ingestion pipeline

### 🛠️ Development & Local Builds
For local development with custom changes:
```bash
# Local builds (default behavior)
docker-compose up -d --build

# Or explicitly use local build file
docker-compose -f docker-compose-local-builld.yml up -d --build
```

> 📖 **Detailed deployment guide**: See [DOCKER_COMPOSE_GUIDE.md](./DOCKER_COMPOSE_GUIDE.md) for complete Docker options
> 
> 🚀 **Interactive helper**: Use `./docker-helper.sh` (Linux/Mac) or `.\docker-helper.ps1` (Windows) for guided deployment

---
```

## �🚀 Quick Start

Services will be available at:

- **API**: http://localhost:8000┌──────────────────────────────────────────────┐- Performance benchmarks and accuracy reports

- **API Docs**: http://localhost:8000/docs

- **PostgreSQL**: localhost:5432### Prerequisites



### 3. Run Ingestion│  API SERVICE (services/api/)                 │



```bash- Docker & Docker Compose

# Sync files from Google Drive

make ingest-sync- Google Cloud service account JSON file│  ─────────────────────────────────────────   │**Use this for**: Building your Custom GPT API, implementing semantic search

# or

docker-compose run --rm ingest python main.py sync --max-files 10- S3 credentials (AWS or DigitalOcean Spaces)



# Full pipeline (sync + process + index)- OpenAI API key with Vector Store access│  • FastAPI REST endpoints                    │

make ingest-full

# or

docker-compose run --rm ingest python main.py full --max-files 10

### 1. Configure Environment│  • Semantic search over Vector Store         │### 📚 Quick Links

# Show statistics

make ingest-stats

```

```bash│  • Metadata enrichment (Drive/S3 URLs)       │

### 4. Test API

# Copy example env file

```bash

# Check healthcp .env.example .env│  • CORS support for web clients              │- **[api-reference/QUICK_START.md](api-reference/QUICK_START.md)** - 5-minute API setup

curl http://localhost:8000/health



# Perform search

curl -X POST http://localhost:8000/api/search \# Edit with your credentials└──────────────────────────────────────────────┘- **[api-reference/README.md](api-reference/README.md)** - Complete API guide

  -H "Content-Type: application/json" \

  -d '{"query": "Your question here", "max_results": 5}'nano .env



# Or use GET``````

curl "http://localhost:8000/api/search?q=Your+question&max_results=5"



# Interactive docs

open http://localhost:8000/docsRequired environment variables:## 🏗️ Architecture

```

```env

## 🎯 Service Details

# Google Drive## 📁 Repository Structure

### Ingest Service

GOOGLE_SERVICE_ACCOUNT_FILE=./google-service-account.json

**Purpose**: Batch processing of documents from Drive to Vector Store

GOOGLE_DRIVE_FOLDER_ID=your-folder-id```

**Key Dependencies**:

- `boto3` - S3 storage

- `google-api-python-client` - Google Drive API

- `openai` - Vector Store indexing# S3 Storage```┌─────────────────┐

- `unstructured` - Document processing

- `docling` - Advanced document processing (optional)S3_ENDPOINT=https://your-s3-endpoint.com



**Commands**:S3_ACCESS_KEY=your-access-keyai-knowledge-base-ingest/│  Google Drive   │

```bash

# Sync from DriveS3_SECRET_KEY=your-secret-key

docker-compose run --rm ingest python main.py sync --max-files 10

S3_BUCKET=your-bucket-name├── docker-compose.yml       # Orchestrates all services│  (Source docs)  │

# Process files

docker-compose run --rm ingest python main.py process --max-files 10S3_REGION=us-east-1



# Index to Vector Store├── .env                     # Shared configuration└────────┬────────┘

docker-compose run --rm ingest python main.py index --max-files 10

# OpenAI

# Full pipeline

docker-compose run --rm ingest python main.py full --max-files 10OPENAI_API_KEY=sk-proj-...├── services/         │



# StatisticsVECTOR_STORE_ID=vs_...

docker-compose run --rm ingest python main.py stats

│   ├── ingest/             # Ingestion service         ▼

# Cleanup stale files

docker-compose run --rm ingest python main.py cleanup# PostgreSQL

```

POSTGRES_DB=ai_knowledge_base│   │   ├── Dockerfile┌─────────────────────────────────────────┐

### API Service

POSTGRES_USER=postgres

**Purpose**: REST API for semantic search

POSTGRES_PASSWORD=your-secure-password│   │   ├── pyproject.toml│  1. SYNC (drive_sync.py)                │

**Endpoints**:

- `GET /` - Service information

- `GET /health` - Health check

- `POST /api/search` - Semantic search (JSON body)# API│   │   ├── main.py│     - List changed files                │

- `GET /api/search` - Semantic search (query params)

- `GET /docs` - Interactive API docs (Swagger UI)API_PORT=8000



**Features**:```│   │   ├── purge.py│     - Download from Drive               │

- Automatic metadata enrichment

- Drive URLs and S3 presigned URLs

- CORS support

- Health checks### 2. Start Services│   │   └── src/            # Pipeline modules│     - Upload to S3                      │



### PostgreSQL Database



**Purpose**: Shared metadata storage```bash│   │       ├── config.py│     - Store metadata in SQLite          │



**Schema**:# Start all services

```sql

-- File state trackingdocker-compose up -d│   │       ├── database.py└────────┬────────────────────────────────┘

CREATE TABLE file_state (

    id SERIAL PRIMARY KEY,

    sha256 VARCHAR(64) UNIQUE NOT NULL,

    s3_key TEXT NOT NULL,# Or use Makefile│   │       ├── drive_sync.py         │

    original_name TEXT NOT NULL,

    status VARCHAR(20) NOT NULL,make up

    synced_at TIMESTAMP,

    processed_at TIMESTAMP,│   │       ├── processor.py         ▼

    indexed_at TIMESTAMP,

    openai_file_id TEXT,# Check status

    error_message TEXT

);docker-compose ps│   │       ├── indexer.py┌─────────────────────────────────────────┐



-- Google Drive mapping```

CREATE TABLE drive_file_mapping (

    id SERIAL PRIMARY KEY,│   │       └── utils.py│  2. PROCESS (processor.py)              │

    sha256 VARCHAR(64) NOT NULL,

    drive_file_id VARCHAR(255) NOT NULL,Services will be available at:

    drive_file_name TEXT NOT NULL,

    drive_parent_path TEXT,- **API**: http://localhost:8000│   └── api/                # API service│     - Fetch from S3                     │

    drive_modified_time TIMESTAMP,

    FOREIGN KEY (sha256) REFERENCES file_state(sha256)- **API Docs**: http://localhost:8000/docs

);

```- **PostgreSQL**: localhost:5432│       ├── Dockerfile│     - Process with Unstructured.io      │



## 🔧 Processing Engines



The system supports two processing engines:### 3. Run Ingestion│       ├── pyproject.toml│     - Extract text, tables, images      │



### Unstructured.io (Default)



Standard document processing with Tesseract OCR.```bash│       ├── main.py         # FastAPI app│     - Save structured data to S3        │



**Configuration:**# Sync files from Google Drive

```env

PROCESSING_ENGINE=unstructuredmake ingest-sync│       └── README.md└────────┬────────────────────────────────┘

```

# or

**Best for:**

- Simple PDFs with good text layersdocker-compose run --rm ingest python main.py sync --max-files 10├── data/                   # Shared volume (SQLite)         │

- Mixed document workflows

- Standard processing needs



### IBM Docling (Advanced)# Full pipeline (sync + process + index)│   └── pipeline.db         ▼



IBM Research's advanced document parsing library with superior OCR and layout analysis.make ingest-full



**Configuration:**# or└── README.md              # This file┌─────────────────────────────────────────┐

```env

PROCESSING_ENGINE=doclingdocker-compose run --rm ingest python main.py full --max-files 10

```

```│  3. INDEX (indexer.py)                  │

**Features:**

- **Superior OCR**: Multiple engines (Tesseract, RapidOCR, EasyOCR)# Show statistics

- **Better Layout Analysis**: Advanced table/equation recognition

- **2-3x Faster**: For complex documentsmake ingest-stats│     - Upload to OpenAI                  │

- **Clean Markdown Export**: Well-structured output

- **Multi-Format**: PDF, DOCX, PPTX, images```



**Best for:**## 🚀 Quick Start│     - Add to Vector Store               │

- Scanned documents requiring high-quality OCR

- Complex layouts with tables and multi-column text### 4. Test API

- Academic papers with equations and figures

- Technical documents with diagrams│     - Enable semantic search            │

- OCR failures from Unstructured

```bash

**Comparison:**

# Check health### Prerequisites└────────┬────────────────────────────────┘

| Feature | Unstructured | Docling |

|---------|-------------|---------|curl http://localhost:8000/health

| **PDF Layout Analysis** | Good | Excellent |

| **OCR Quality** | Good | Excellent |         │

| **Table Recognition** | Good | Excellent |

| **Processing Speed** | Moderate | Fast (2-3x) |# Perform search

| **Memory Usage** | Moderate | Low |

| **Output Format** | Text + JSONL | Markdown + JSON |curl -X POST http://localhost:8000/api/search \- Docker & Docker Compose         ▼



**Switching Engines:**  -H "Content-Type: application/json" \



You can switch at any time - previously processed files remain unchanged:  -d '{"query": "Your question here", "max_results": 5}'- Google Cloud service account JSON file┌─────────────────┐



```bash

# Edit .env

PROCESSING_ENGINE=docling# Or use GET- S3 credentials (AWS or DigitalOcean Spaces)│  OpenAI Vector  │



# Restart servicescurl "http://localhost:8000/api/search?q=Your+question&max_results=5"

docker-compose restart ingest

```- OpenAI API key with Vector Store access│     Store       │



## 📖 Usage Examples# Interactive docs



### Running Ingestionopen http://localhost:8000/docs│  (Searchable)   │



```bash```

# Dry run (test without changes)

docker-compose run --rm ingest python main.py --dry-run sync### 1. Configure Environment└─────────────────┘



# Sync limited files## 🎯 Service Details

docker-compose run --rm ingest python main.py sync --max-files 10

```

# Full pipeline with limits

docker-compose run --rm ingest python main.py full --max-files 50### Ingest Service



# Show statistics```bash

docker-compose run --rm ingest python main.py stats

**Purpose**: Batch processing of documents from Drive to Vector Store

# Cleanup stale files

docker-compose run --rm ingest python main.py cleanup# Copy example env file## 🚀 Quick Start

```

**Technology**:

### Using the API

- Python 3.11cp .env.example .env

**Python:**

```python- uv for dependency management

import httpx

- Isolated virtual environment### Prerequisites

response = httpx.post(

    "http://localhost:8000/api/search",- 150 packages (optimized)

    json={"query": "Holocaust education", "max_results": 10}

)# Edit with your credentials



results = response.json()**Key Dependencies**:



for result in results["results"]:- `boto3` - S3 storagenano .env- Python 3.11+

    print(f"File: {result['metadata']['original_name']}")

    print(f"Score: {result['score']}")- `google-api-python-client` - Google Drive API

    print(f"Drive URL: {result['metadata']['drive_url']}")

    print()- `openai` - Vector Store indexing```- Google Cloud service account with Drive API access

```

- `unstructured` - Document processing

**JavaScript:**

```javascript- `tqdm` - Progress tracking- AWS S3 bucket

const response = await fetch('http://localhost:8000/api/search', {

  method: 'POST',

  headers: {'Content-Type': 'application/json'},

  body: JSON.stringify({**Commands**:Required environment variables:- OpenAI API key with Vector Store access

    query: 'Holocaust education',

    max_results: 10```bash

  })

});# Sync from Drive```env- Unstructured.io API key (optional, for cloud processing)



const data = await response.json();docker-compose run --rm ingest python main.py sync --max-files 10

console.log(`Found ${data.count} results`);

```# Google Drive



**cURL:**# Process files

```bash

GOOGLE_SERVICE_ACCOUNT_FILE=./google-service-account.json

### Installation

  -H "Content-Type: application/json" \

  -d '{

    "query": "What is Centropa?",

    "max_results": 5# Index to Vector StoreGOOGLE_DRIVE_FOLDER_ID=your-folder-id

  }'

```docker-compose run --rm ingest python main.py index --max-files 10



### Managing Services```bash



```bash# Full pipeline

# Start services

docker-compose up -ddocker-compose run --rm ingest python main.py full --max-files 10# S3 Storage# Clone the repository



# Stop services

docker-compose down

# StatisticsS3_ENDPOINT=https://your-s3-endpoint.comgit clone <your-repo-url>

# Rebuild after code changes

docker-compose builddocker-compose run --rm ingest python main.py stats



# View logsS3_ACCESS_KEY=your-access-keycd ai-knowledge-base-ingest

docker-compose logs -f api

docker-compose logs -f ingest# Cleanup stale files



# Restart specific servicedocker-compose run --rm ingest python main.py cleanupS3_SECRET_KEY=your-secret-key

docker-compose restart api

```

# Remove everything (including volumes)

docker-compose down -vS3_BUCKET=your-bucket-name# Install dependencies with uv (recommended)

```

### API Service

## 🔧 Development

S3_REGION=us-east-1uv sync

### Local Development (Without Docker)

**Purpose**: REST API for semantic search

**API Service:**

```bash

cd services/api

uv sync**Technology**:

uv run uvicorn main:app --reload --port 8000

```- Python 3.11# OpenAI# Or with pip



**Ingest Service:**- FastAPI framework

```bash

cd services/ingest- uv for dependency managementOPENAI_API_KEY=sk-proj-...pip install -e .

uv sync

uv run python main.py sync --max-files 5- Isolated virtual environment

```

- 32 packages (minimal!)VECTOR_STORE_ID=vs_...```

### Building Images



```bash

# Build all services**Key Dependencies**:

docker-compose build

- `fastapi` - Web framework

# Build specific service

docker-compose build api- `uvicorn` - ASGI server# PostgreSQL### Configuration

docker-compose build ingest

- `httpx` - HTTP client

# Build with no cache

docker-compose build --no-cache- `boto3` - S3 presigned URLsPOSTGRES_DB=ai_knowledge_base

```

- `python-dotenv` - Configuration

### Makefile Commands

POSTGRES_USER=postgres1. Copy the example environment file:

```bash

make help           # Show all commands**Endpoints**:

make build          # Build all Docker images

make up             # Start all services- `GET /` - Service informationPOSTGRES_PASSWORD=your-secure-password```bash

make down           # Stop all services

make logs           # View logs from all services- `GET /health` - Health check

make restart        # Restart all services

make clean          # Remove all containers and volumes- `POST /api/search` - Semantic search (JSON body)cp .env.example .env



# Ingestion- `GET /api/search` - Semantic search (URL params)

make ingest-sync    # Sync files from Drive

make ingest-process # Process files- `GET /docs` - Interactive API docs (Swagger UI)# API```

make ingest-full    # Run full pipeline

make ingest-stats   # Show statistics



# API**Features**:API_PORT=8000

make api-test       # Test API health

make api-search     # Example search query- Automatic metadata enrichment



# Development- Drive URLs and S3 presigned URLs```2. Edit `.env` with your credentials:

make dev-api        # Run API locally (no Docker)

make dev-ingest     # Run ingest locally (no Docker)- CORS support

```

- Health checks```env

## 📊 Monitoring

- OpenAPI/Swagger documentation

### Check Service Status

### 2. Start Services# Google Drive

```bash

# All services### PostgreSQL Database

docker-compose ps

GOOGLE_CREDENTIALS_FILE=path/to/service-account.json

# Logs (all services)

docker-compose logs -f**Purpose**: Shared metadata storage



# Logs (specific service)```bashDRIVE_FOLDER_ID=your-drive-folder-id

docker-compose logs -f api

docker-compose logs -f ingest**Technology**:

docker-compose logs -f postgres

- PostgreSQL 16 Alpine# Start all services

# Resource usage

docker stats- Persistent volumes

```

- Health checksdocker-compose up -d# AWS S3

### Health Checks

- Automatic initialization

```bash

# API healthAWS_ACCESS_KEY_ID=your-access-key

curl http://localhost:8000/health

**Schema**:

# PostgreSQL health

docker-compose exec postgres pg_isready```sql# Check statusAWS_SECRET_ACCESS_KEY=your-secret-key



# Check all services-- File state tracking

docker-compose ps

```CREATE TABLE file_state (docker-compose psAWS_REGION=us-east-1



### Database Queries    id SERIAL PRIMARY KEY,



```bash    sha256 VARCHAR(64) UNIQUE NOT NULL,S3_BUCKET_NAME=your-bucket-name

# Connect to PostgreSQL

docker-compose exec postgres psql -U postgres -d ai_knowledge_base    s3_key TEXT NOT NULL,



# Check file counts    original_name TEXT NOT NULL,# View logs

SELECT status, COUNT(*) FROM file_state GROUP BY status;

    status VARCHAR(20) NOT NULL,

# View recent files

SELECT original_name, status, synced_at     synced_at TIMESTAMP,docker-compose logs -f# OpenAI

FROM file_state 

ORDER BY synced_at DESC     processed_at TIMESTAMP,

LIMIT 10;

    indexed_at TIMESTAMP,```OPENAI_API_KEY=sk-proj-...

# Check for errors

SELECT original_name, error_message     openai_file_id TEXT,

FROM file_state 

WHERE status LIKE 'failed%'     error_message TEXTVECTOR_STORE_ID=vs_...

ORDER BY synced_at DESC;

```);



## 🔒 Security Best PracticesServices will be available at:



1. **Never commit secrets**-- Google Drive mapping

   - Keep `.env` file local (in `.gitignore`)

   - Rotate API keys regularlyCREATE TABLE drive_file_mapping (- **API**: http://localhost:8000# Unstructured.io (optional)

   - Use environment-specific configurations

    id SERIAL PRIMARY KEY,

2. **Secure service account**

   - Limit Drive folder access    sha256 VARCHAR(64) NOT NULL,- **API Docs**: http://localhost:8000/docsUNSTRUCTURED_API_KEY=your-api-key

   - Use least-privilege permissions

   - Store JSON file securely    drive_file_id VARCHAR(255) NOT NULL,



3. **Database security**    drive_file_name TEXT NOT NULL,- **PostgreSQL**: localhost:5432UNSTRUCTURED_API_URL=https://api.unstructuredapp.io/general/v0/general

   - Use strong PostgreSQL password

   - Don't expose port 5432 publicly    drive_parent_path TEXT,

   - Regular backups

   - Enable SSL in production    drive_modified_time TIMESTAMP,```



4. **S3 bucket**    FOREIGN KEY (sha256) REFERENCES file_state(sha256)

   - Enable encryption at rest

   - Use presigned URLs (1 hour expiry));### 3. Run Ingestion

   - Restrict IAM policies

   - Enable versioning```



5. **API security** (Production)## 📖 Usage

   - Add authentication middleware

   - Enable HTTPS/TLS## 🛠️ Development

   - Configure CORS appropriately

   - Implement rate limiting```bash

   - Use API keys or JWT tokens

### Local Development (Without Docker)

## 🐛 Troubleshooting

# Sync files from Google Drive### Basic Commands

### Services won't start

**API Service:**

```bash

# Check logs```bashdocker-compose run --rm ingest uv run python main.py sync --max-files 10

docker-compose logs

cd services/api

# Rebuild images

docker-compose build --no-cacheuv sync```bash

docker-compose up -d

```uv run uvicorn main:app --reload --port 8000



### API can't connect to database```# Process files with Unstructured.io# Full pipeline - sync, process, and index



```bash

# Check PostgreSQL is running

docker-compose ps postgres**Ingest Service:**docker-compose run --rm ingest uv run python main.py process --max-files 10uv run python main.py



# Test connectivity```bash

docker-compose exec api ping postgres

cd services/ingest

# Verify environment variables

docker-compose exec api env | grep POSTGRESuv sync

```

uv run python main.py sync --max-files 5# Index to OpenAI Vector Store# Individual stages

### Ingest can't access service account

```

```bash

# Check file existsdocker-compose run --rm ingest uv run python main.py index --max-files 10uv run python main.py sync              # Sync from Drive to S3

ls -la google-service-account.json

### Building Images

# Verify mount in container

docker-compose run --rm ingest ls -la /app/service-account.jsonuv run python main.py process           # Process files with Unstructured

```

```bash

### Port conflicts

# Build all services# Or run full pipelineuv run python main.py index             # Index files to OpenAI

```bash

# Change ports in .envdocker-compose build

API_PORT=8001

POSTGRES_PORT=5433# ordocker-compose run --rm ingest uv run python main.py full --max-files 10



# Restart servicesmake build

docker-compose down

docker-compose up -d```# Dry run (test without changes)

```

# Build specific service

### Dependencies not updating

docker-compose build apiuv run python main.py --dry-run sync

```bash

# Rebuild without cachedocker-compose build ingest

cd services/ingest  # or services/api

uv lock --upgrade### 4. Test API

cd ../..

docker-compose build --no-cache ingest  # or api# Build with no cache

```

docker-compose build --no-cache# Limit number of files

## 📈 Performance

```

Typical processing times:

- **Sync**: ~1-2 seconds per file (depends on Drive API)```bashuv run python main.py --max-files 10 sync

- **Process (Unstructured)**: ~5-10 seconds per file

- **Process (Docling)**: ~2-5 seconds per file (2-3x faster)### Makefile Commands

- **Index**: ~2-3 seconds per file (depends on OpenAI API)

# Check health```

Batch recommendations:

- Start with `--max-files 10` to test```bash

- Scale up to `--max-files 100` for production

- Use `--dry-run` to preview changesmake help           # Show all commandscurl http://localhost:8000/health



## 📚 Additional Resourcesmake build          # Build all Docker images



- **api-reference/** - Complete query API documentation and samplesmake up             # Start all services### Pipeline Stages

- **test/** - Test files and Custom GPT documentation

- **Makefile** - Run `make help` for all commandsmake down           # Stop all services

- **API Docs** - http://localhost:8000/docs (when running)

make logs           # View logs from all services# Perform search

## 🎓 Next Steps

make restart        # Restart all services

### For Ingestion Setup

1. ✅ Configure `.env` with your credentialsmake clean          # Remove all containers and volumescurl -X POST http://localhost:8000/api/search \#### 1. Sync Stage

2. ✅ Start services: `make up`

3. ✅ Run ingestion: `make ingest-sync`

4. ✅ Monitor logs: `make logs`

# Ingestion  -H "Content-Type: application/json" \Syncs files from Google Drive to S3:

### For API Development

1. ✅ Check API health: `make api-test`make ingest-sync    # Sync files from Drive

2. ✅ Visit interactive docs: http://localhost:8000/docs

3. ✅ Test search: `curl "http://localhost:8000/api/search?q=test"`make ingest-process # Process files  -d '{"query": "What is Centropa?", "max_results": 5}'- Lists all files in the configured Drive folder (recursive)

4. ✅ Review `api-reference/` for advanced examples

make ingest-full    # Run full pipeline

### Production Deployment

1. ✅ Set up managed PostgreSQLmake ingest-stats   # Show statistics- Detects changes using modification timestamps and SHA256 hashes

2. ✅ Configure HTTPS/TLS for API

3. ✅ Add authentication middleware

4. ✅ Set up monitoring (Prometheus, Grafana)

5. ✅ Configure automated backups# API# Or use GET- Downloads changed files from Drive

6. ✅ Schedule ingestion with cron

7. ✅ Enable rate limitingmake api-test       # Test API health



## 🤝 Contributingmake api-search     # Example search querycurl "http://localhost:8000/api/search?q=Holocaust+education&max_results=5"- Uploads to S3 with metadata



1. Make changes in appropriate service directory

2. Test locally with `docker-compose up`

3. Update documentation if needed# Development```- Exports Google Workspace files (Docs, Sheets, Slides) to Office formats

4. Commit with clear messages

make dev-api        # Run API locally (no Docker)

## 📝 License

make dev-ingest     # Run ingest locally (no Docker)- Stores file state in SQLite database

Internal use only.

```

---

## 🐳 Docker Services

**Ready to start?**

## 📊 Monitoring

```bash

# 1. Configure```bash

cp .env.example .env

nano .env### Check Service Status



# 2. Start everything### Ingest Serviceuv run python main.py sync --max-files 100

make up

```bash

# 3. Run ingestion

make ingest-sync# All services```



# 4. Test APIdocker-compose ps

curl http://localhost:8000/health

**Purpose**: Sync, process, and index documents

# 5. Interactive docs

open http://localhost:8000/docs# Logs (all services)

```

docker-compose logs -f#### 2. Process Stage

🚀 **Your AI Knowledge Base is ready!**



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

ls -la google-service-account.json

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

ls -la google-service-account.json

# Check permissions in Google Cloud Console

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
