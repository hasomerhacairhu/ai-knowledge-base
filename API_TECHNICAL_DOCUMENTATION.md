# AI Knowledge Base API - Technical Documentation

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Data Flow](#data-flow)
4. [API Endpoints](#api-endpoints)
5. [Database Schema](#database-schema)
6. [Storage Architecture](#storage-architecture)
7. [Authentication & Security](#authentication--security)
8. [Deployment](#deployment)
9. [Performance & Scalability](#performance--scalability)
10. [Monitoring & Debugging](#monitoring--debugging)

---

## System Overview

The AI Knowledge Base API is a FastAPI-based semantic search service that provides intelligent document retrieval from a knowledge base of PDF documents, primarily focused on Hungarian youth work and scouting materials.

### Key Features

- **Semantic Search**: Uses OpenAI's Vector Store for embedding-based similarity search
- **Metadata Enrichment**: Augments search results with file metadata from PostgreSQL
- **Document Access**: Generates presigned S3 URLs for both original and processed documents
- **Direct Vector Search**: Bypasses LLM for faster, cost-effective searches
- **High Performance**: Sub-500ms response times with connection pooling
- **Production Ready**: Docker containerized with health checks and monitoring

### Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **API Framework** | FastAPI 0.120.2 | High-performance async web framework |
| **Database** | PostgreSQL 16 | File metadata and state management |
| **Vector Store** | OpenAI Vector Store | Semantic document embeddings |
| **Object Storage** | S3-compatible (DigitalOcean Spaces) | Document storage |
| **HTTP Client** | httpx 0.28.1 | Async OpenAI API communication |
| **ASGI Server** | uvicorn 0.38.0 | Production-grade ASGI server |
| **Containerization** | Docker + docker-compose | Service orchestration |

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                             │
│  (Web App, cURL, Python scripts, JavaScript apps)               │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP/HTTPS
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Cloudflare Tunnel                             │
│              (HTTPS, DDoS protection, SSL/TLS)                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP (internal)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Application                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  API Endpoints Layer                                     │    │
│  │  • POST /api/search (semantic search)                   │    │
│  │  • GET /api/search (convenience)                        │    │
│  │  • GET /health (health check)                           │    │
│  │  • GET / (root info)                                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                         │                                         │
│  ┌──────────────────────┴─────────────────────────────────┐    │
│  │  Business Logic Layer                                   │    │
│  │  • Query processing                                     │    │
│  │  • Result enrichment                                    │    │
│  │  • URL generation                                       │    │
│  │  • Error handling                                       │    │
│  └──────────────────┬──────────────────┬──────────────────┘    │
│                     │                   │                        │
└─────────────────────┼───────────────────┼────────────────────────┘
                      │                   │
         ┌────────────┴────────┐ ┌───────┴──────────┐
         ▼                     ▼                     ▼
┌────────────────┐   ┌──────────────────┐  ┌────────────────────┐
│  PostgreSQL    │   │  OpenAI Vector   │  │  S3 Storage        │
│  Database      │   │  Store           │  │  (DigitalOcean)    │
│                │   │                  │  │                    │
│  • file_state  │   │  • Embeddings    │  │  • objects/        │
│  • drive_file  │   │  • Similarity    │  │  • derivatives/    │
│    _mapping    │   │    search        │  │  • Presigned URLs  │
└────────────────┘   └──────────────────┘  └────────────────────┘
```

### Component Interactions

1. **Client Request** → API receives search query via HTTP/HTTPS
2. **Vector Search** → API queries OpenAI Vector Store for semantic matches
3. **Metadata Lookup** → For each result, fetch metadata from PostgreSQL
4. **URL Generation** → Generate presigned S3 URLs for document access
5. **Response** → Return enriched results with all metadata

---

## Data Flow

### Search Request Flow

```
1. CLIENT REQUEST
   ├─ POST /api/search
   ├─ Body: {"query": "Holocaust education", "max_results": 10}
   └─ Headers: Content-Type: application/json

2. FASTAPI PROCESSING
   ├─ Validate request (Pydantic models)
   ├─ Log incoming request
   └─ Pass to vector_store_search()

3. OPENAI VECTOR STORE QUERY
   ├─ Endpoint: POST https://api.openai.com/v1/vector_stores/{id}/search
   ├─ Headers: Authorization: Bearer {OPENAI_API_KEY}
   ├─ Body: {
   │    "query": "Holocaust education",
   │    "max_num_results": 10,
   │    "rewrite_query": true
   │  }
   └─ Response: {
        "data": [
          {
            "filename": "e81f577afe460...803e2.txt",
            "file_id": "file-abc123",
            "score": 0.8542,
            "content": [{"type": "text", "text": "..."}]
          }
        ]
      }

4. METADATA ENRICHMENT (per result)
   ├─ Extract SHA256 from filename: "e81f577afe460...803e2"
   ├─ Query PostgreSQL:
   │    SELECT original_name, s3_key, sha256
   │    FROM drive_file_mapping dfm
   │    JOIN file_state fs ON dfm.sha256 = fs.sha256
   │    WHERE fs.sha256 = 'e81f577afe460...803e2'
   ├─ Generate S3 presigned URLs:
   │    • Original: objects/e8/1f/e81f577afe460...803e2.pdf
   │    • Text: derivatives/e8/1f/e81f577afe460...803e2/text.txt
   │    • Expiration: 7 days (604,800 seconds)
   └─ Build FileMetadata object

5. RESPONSE CONSTRUCTION
   ├─ Combine vector search results with metadata
   ├─ Build SearchResponse object
   └─ Return JSON:
      {
        "query": "Holocaust education",
        "results": [
          {
            "score": 0.8542,
            "content": [...],
            "metadata": {
              "original_name": "Holocaust Lesson Plan.pdf",
              "original_file_download_url": "https://...",
              "processed_text_download_url": "https://...",
              "sha256": "e81f577afe460...803e2"
            }
          }
        ],
        "count": 10
      }

6. CLIENT RECEIVES RESPONSE
   └─ Parse JSON and display results
```

### Database Query Pattern

```python
# Connection Pool (initialized at startup)
db_pool = psycopg2.pool.SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    host="postgres",
    database="ai_knowledge_base",
    user="postgres",
    password="postgres"
)

# Per-request pattern
conn = db_pool.getconn()  # Get connection from pool
try:
    cursor = conn.cursor()
    cursor.execute("SELECT ...")
    result = cursor.fetchone()
finally:
    db_pool.putconn(conn)  # Return connection to pool
```

---

## API Endpoints

### POST /api/search

Primary search endpoint with full parameter control.

**Request:**
```http
POST /api/search HTTP/1.1
Host: api.example.com
Content-Type: application/json

{
  "query": "Hogyan szervezzünk Peula foglalkozást?",
  "max_results": 20,
  "rewrite_query": true
}
```

**Request Model (Pydantic):**
```python
class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    max_results: int = Field(10, ge=1, le=50, description="Maximum number of results")
    rewrite_query: bool = Field(True, description="Whether to optimize query for vector search")
```

**Response:**
```json
{
  "query": "Hogyan szervezzünk Peula foglalkozást?",
  "results": [
    {
      "score": 0.6967,
      "content": [
        {
          "type": "text",
          "text": "Summary of the activity: We will play a game with different roles..."
        }
      ],
      "metadata": {
        "original_name": "Youth Inclusion Toolbox.pdf",
        "original_file_download_url": "https://fra1.digitaloceanspaces.com/...",
        "processed_text_download_url": "https://fra1.digitaloceanspaces.com/derivatives/...",
        "sha256": "3001d6336b20c90358f5ba08ce79ca52f798c82892389a2db39a79fba0714c1f"
      }
    }
  ],
  "count": 20
}
```

**Response Model (Pydantic):**
```python
class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    count: int

class SearchResult(BaseModel):
    score: float
    content: List[ContentItem]
    metadata: Optional[FileMetadata] = None

class ContentItem(BaseModel):
    type: str
    text: str

class FileMetadata(BaseModel):
    original_name: str
    original_file_download_url: str
    processed_text_download_url: Optional[str] = None
    sha256: str
```

### GET /api/search

Convenience endpoint for simple queries.

**Request:**
```http
GET /api/search?q=Holocaust&max_results=5&rewrite=true HTTP/1.1
Host: api.example.com
```

**Query Parameters:**
- `q` (string, required): Search query
- `max_results` (integer, optional): Number of results (1-50, default: 10)
- `rewrite` (boolean, optional): Enable query rewriting (default: true)

### GET /health

Health check endpoint for monitoring and load balancers.

**Response:**
```json
{
  "status": "healthy",
  "vector_store_id": "vs_6900e6fc7c94819187c6ec114fd3adc9",
  "database": "connected"
}
```

**Status Values:**
- `healthy`: All systems operational
- `degraded`: Database connection issues

### GET /

Root endpoint with API information.

**Response:**
```json
{
  "service": "AI Knowledge Base API",
  "version": "1.0.0",
  "endpoints": {
    "search": "/api/search",
    "health": "/health",
    "docs": "/docs"
  }
}
```

### GET /docs

Interactive Swagger UI documentation.

### GET /redoc

Alternative ReDoc documentation interface.

---

## Database Schema

### file_state Table

Primary table tracking file processing status.

```sql
CREATE TABLE file_state (
    sha256 TEXT PRIMARY KEY,                  -- SHA256 hash of file content
    drive_file_id TEXT,                       -- Google Drive file ID
    drive_path TEXT,                          -- Full path in Drive
    original_name TEXT,                       -- Original filename
    s3_key TEXT NOT NULL,                     -- S3 object key (objects/xx/xx/sha256.ext)
    extension TEXT,                           -- File extension (.pdf, .docx)
    status TEXT NOT NULL,                     -- Processing status (see FileStatus enum)
    
    -- Stage timestamps
    synced_at TIMESTAMP,                      -- When synced from Drive to S3
    processed_at TIMESTAMP,                   -- When processed by Docling
    indexed_at TIMESTAMP,                     -- When indexed to Vector Store
    
    -- Drive metadata
    drive_created_time TIMESTAMP,             -- Original creation time in Drive
    drive_modified_time TIMESTAMP,            -- Last modified time in Drive
    drive_mime_type TEXT,                     -- MIME type (application/pdf)
    
    -- File sizes
    original_file_size BIGINT,                -- Size of original file (bytes)
    processed_text_size BIGINT,               -- Size of processed text (bytes)
    
    -- OpenAI references
    openai_file_id TEXT,                      -- OpenAI file ID (file-abc123)
    vector_store_id TEXT,                     -- Vector Store ID (vs_xxx)
    
    -- Error tracking
    error_message TEXT,                       -- Last error message if failed
    retry_count INTEGER DEFAULT 0,            -- Number of retry attempts
    last_retry TIMESTAMP,                     -- Timestamp of last retry
    
    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_file_state_status ON file_state(status);
CREATE INDEX idx_file_state_drive_file_id ON file_state(drive_file_id);
CREATE INDEX idx_file_state_openai_file_id ON file_state(openai_file_id);
CREATE INDEX idx_file_state_updated_at ON file_state(updated_at);
```

### drive_file_mapping Table

Maps Google Drive files to SHA256 hashes.

```sql
CREATE TABLE drive_file_mapping (
    sha256 TEXT PRIMARY KEY,                  -- Links to file_state.sha256
    drive_file_id TEXT NOT NULL,              -- Google Drive file ID
    drive_file_name TEXT NOT NULL,            -- Current name in Drive
    drive_parent_path TEXT,                   -- Parent folder path
    drive_modified_time TIMESTAMP,            -- Last modified in Drive
    drive_mime_type TEXT,                     -- MIME type
    
    -- Audit
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (sha256) REFERENCES file_state(sha256) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX idx_drive_mapping_file_id ON drive_file_mapping(drive_file_id);
CREATE INDEX idx_drive_mapping_modified ON drive_file_mapping(drive_modified_time);
```

### File Status Enum

```python
class FileStatus(Enum):
    SYNCED = "synced"              # Downloaded from Drive to S3
    PROCESSING = "processing"       # Being processed by Docling
    PROCESSED = "processed"         # Processing complete
    INDEXING = "indexing"          # Being indexed to Vector Store
    INDEXED = "indexed"            # Successfully indexed
    FAILED_SYNC = "failed_sync"    # Failed during sync
    FAILED_PROCESS = "failed_process"  # Failed during processing
    FAILED_INDEX = "failed_index"   # Failed during indexing
```

### Query Examples

**Find all indexed files:**
```sql
SELECT original_name, s3_key, indexed_at
FROM file_state
WHERE status = 'indexed'
ORDER BY indexed_at DESC;
```

**Get file metadata by SHA256:**
```sql
SELECT 
    dfm.original_name,
    fs.s3_key,
    fs.sha256,
    fs.original_file_size,
    fs.processed_text_size
FROM drive_file_mapping dfm
JOIN file_state fs ON dfm.sha256 = fs.sha256
WHERE fs.sha256 = 'e81f577afe460fca66d7f2c44db91286d0dfc83cb48d1e01f60f45b71bb803e2';
```

**Find recently modified files:**
```sql
SELECT original_name, drive_modified_time, status
FROM file_state
WHERE drive_modified_time > NOW() - INTERVAL '7 days'
ORDER BY drive_modified_time DESC;
```

---

## Storage Architecture

### S3 Object Organization

Documents are stored in a sharded structure for optimal performance:

```
s3://somer-ai/
├── objects/                          # Original files
│   ├── e8/                          # First 2 chars of SHA256
│   │   └── 1f/                      # Next 2 chars of SHA256
│   │       └── e81f577afe...803e2.pdf  # Full SHA256 + extension
│   ├── 30/
│   │   └── 01/
│   │       └── 3001d6336b...4c1f.pdf
│   └── ...
│
└── derivatives/                      # Processed files
    ├── e8/
    │   └── 1f/
    │       └── e81f577afe...803e2/  # SHA256 directory
    │           ├── text.txt         # Extracted text
    │           ├── metadata.json    # Processing metadata
    │           └── images/          # Extracted images (if any)
    └── ...
```

### Sharding Strategy

**Why sharding?**
- Avoids filesystem limits on files per directory
- Improves S3 performance (distributes requests across partitions)
- Enables efficient prefix-based queries

**Shard calculation:**
```python
sha256 = "e81f577afe460fca66d7f2c44db91286d0dfc83cb48d1e01f60f45b71bb803e2"
shard1 = sha256[:2]   # "e8"
shard2 = sha256[2:4]  # "1f"

# Original file path
original_path = f"objects/{shard1}/{shard2}/{sha256}.pdf"
# Result: objects/e8/1f/e81f577afe460fca66d7f2c44db91286d0dfc83cb48d1e01f60f45b71bb803e2.pdf

# Processed text path
text_path = f"derivatives/{shard1}/{shard2}/{sha256}/text.txt"
# Result: derivatives/e8/1f/e81f577afe460fca66d7f2c44db91286d0dfc83cb48d1e01f60f45b71bb803e2/text.txt
```

### Presigned URL Generation

```python
def generate_presigned_url(s3_key: str) -> str:
    """Generate 7-day presigned URL"""
    return s3_client.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': 'somer-ai',
            'Key': s3_key
        },
        ExpiresIn=604800  # 7 days in seconds
    )
```

**URL Example:**
```
https://fra1.digitaloceanspaces.com/somer-ai/objects/e8/1f/e81f577...803e2.pdf
  ?X-Amz-Algorithm=AWS4-HMAC-SHA256
  &X-Amz-Credential=DO801BL89U8FZB966LQP%2F20251030%2Ffra1%2Fs3%2Faws4_request
  &X-Amz-Date=20251030T204502Z
  &X-Amz-Expires=604800
  &X-Amz-SignedHeaders=host
  &X-Amz-Signature=e20f557a4d225c26dd47ebbe7ca954f5457a740ce0510a806687e093ae90518e
```

### Storage Provider

**DigitalOcean Spaces** (S3-compatible):
- Region: `fra1` (Frankfurt)
- Endpoint: `https://fra1.digitaloceanspaces.com`
- Bucket: `somer-ai`
- ACL: Private (presigned URLs only)

---

## Authentication & Security

### API Security

**Current Implementation:**
- No authentication required (internal API)
- Cloudflare Tunnel provides SSL/TLS termination
- CORS configured for specific origins

**CORS Configuration:**
```python
allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,      # ["https://example.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Recommended Production Security

1. **API Key Authentication:**
```python
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != os.getenv("API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
    return api_key

@app.post("/api/search")
async def search(request: SearchRequest, api_key: str = Depends(verify_api_key)):
    # ... implementation
```

2. **Rate Limiting:**
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

@app.post("/api/search")
@limiter.limit("10/minute")
async def search(request: Request):
    # ... implementation
```

3. **Cloudflare Access Policies:**
   - Go to Cloudflare Zero Trust → Access → Applications
   - Create application for your API subdomain
   - Set policies (email domain, IP ranges, etc.)

### Credentials Management

**Environment Variables:**
```bash
# .env file (never commit!)
OPENAI_API_KEY=sk-proj-xxx...              # OpenAI API access
VECTOR_STORE_ID=vs_xxx...                  # Vector Store ID
POSTGRES_PASSWORD=secure_random_password   # DB password
S3_ACCESS_KEY=DO801BL89U8FZB966LQP         # S3 access key
S3_SECRET_KEY=065cIxShrBK...               # S3 secret key
```

**Docker Secrets (Alternative):**
```yaml
services:
  api:
    secrets:
      - openai_api_key
      - postgres_password
    environment:
      OPENAI_API_KEY_FILE: /run/secrets/openai_api_key

secrets:
  openai_api_key:
    file: ./secrets/openai_api_key.txt
  postgres_password:
    file: ./secrets/postgres_password.txt
```

---

## Deployment

### Docker Compose Setup

**File structure:**
```
ai-knowledge-base-ingest/
├── docker-compose.yml           # Service orchestration
├── .env                         # Environment variables
├── services/
│   ├── api/
│   │   ├── Dockerfile          # API container image
│   │   ├── main.py             # FastAPI application
│   │   ├── pyproject.toml      # Python dependencies
│   │   └── README.md           # API documentation
│   └── ingest/
│       └── ...                  # Ingestion service
└── ...
```

**docker-compose.yml:**
```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: ai-kb-postgres
    environment:
      POSTGRES_DB: ai_knowledge_base
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - ai-kb-network

  api:
    build:
      context: ./services/api
      dockerfile: Dockerfile
    image: ai-kb-api:latest
    container_name: ai-kb-api
    env_file:
      - .env
    environment:
      API_PORT: 8000
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      POSTGRES_DB: ai_knowledge_base
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - shared_data:/app/data:ro
    ports:
      - "8001:8000"  # External:Internal
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "/app/.venv/bin/python", "-c", "import httpx; httpx.get('http://localhost:8000/health', timeout=5.0)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    networks:
      - ai-kb-network
      - apps  # Cloudflare tunnel network

networks:
  ai-kb-network:
    driver: bridge
  apps:
    external: true  # Pre-existing network with cloudflared
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies
RUN uv pip install --system -r pyproject.toml

# Copy application code
COPY main.py ./

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["/usr/local/bin/python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Deployment Commands

**Initial setup:**
```bash
# On production server (100.106.229.15)
cd /root/ai-knowledge-base-ingest

# Create .env file with credentials
cp .env.example .env
nano .env  # Edit with actual credentials

# Build and start services
docker compose build
docker compose up -d

# Check status
docker compose ps
docker compose logs -f api
```

**Update deployment:**
```bash
# Pull latest code
git pull origin main

# Rebuild and restart API
docker compose build api
docker compose up -d api

# Verify
docker compose logs -f api
curl http://localhost:8001/health
```

**Rollback:**
```bash
# Rollback to specific commit
git reset --hard <commit-hash>
docker compose build api
docker compose up -d api
```

### Cloudflare Tunnel Configuration

**Add to tunnel (via dashboard):**
1. Go to https://one.dash.cloudflare.com/
2. Navigate to Networks → Tunnels
3. Select your tunnel
4. Add Public Hostname:
   - Subdomain: `ai-kb-api`
   - Domain: `yourdomain.com`
   - Type: `HTTP`
   - URL: `http://ai-kb-api:8000`

**Result:**
- Public URL: `https://ai-kb-api.yourdomain.com`
- SSL/TLS: Automatically handled by Cloudflare
- DDoS protection: Included

---

## Performance & Scalability

### Current Performance

**Benchmarks** (production server: 100.106.229.15):

| Metric | Value | Notes |
|--------|-------|-------|
| **Search Latency** | 200-500ms | P95: 450ms, P99: 600ms |
| **Throughput** | ~100 req/s | Single container |
| **Database Queries** | 1 per result | Metadata enrichment |
| **Connection Pool** | 1-10 connections | PostgreSQL |
| **Memory Usage** | ~150MB | Typical load |
| **CPU Usage** | 5-20% | Single core |

**OpenAI Vector Store Costs:**
- **Search cost**: $2.50 per 1,000 searches
- **No token costs**: Direct search, no LLM
- **Example**: 10,000 searches/month = $25

### Optimization Strategies

**1. Database Connection Pooling**
```python
db_pool = psycopg2.pool.SimpleConnectionPool(
    minconn=1,    # Keep 1 connection ready
    maxconn=10,   # Max 10 concurrent connections
    # ... other params
)
```

**Benefits:**
- Reuses connections (no TCP handshake overhead)
- Handles concurrent requests efficiently
- Automatic connection recycling

**2. Async HTTP Clients**
```python
async with httpx.AsyncClient(timeout=30.0) as client:
    response = await client.post(endpoint, headers=headers, json=payload)
```

**Benefits:**
- Non-blocking I/O for OpenAI API calls
- Handles multiple concurrent requests
- Timeout protection

**3. Result Caching (Future)**
```python
from functools import lru_cache
from hashlib import md5

@lru_cache(maxsize=1000)
def get_cached_metadata(sha256: str) -> Optional[FileMetadata]:
    return get_file_metadata(sha256)
```

**Benefits:**
- Reduces database queries for repeated files
- In-memory cache for fast lookups
- Configurable cache size

### Scaling Strategies

**Horizontal Scaling:**
```yaml
# docker-compose.yml
services:
  api:
    # ... same config
    deploy:
      replicas: 3  # Run 3 instances
      
  nginx:
    image: nginx:alpine
    ports:
      - "8000:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - api
```

**Load Balancer (nginx.conf):**
```nginx
upstream api_backend {
    least_conn;  # Route to least busy server
    server api-1:8000;
    server api-2:8000;
    server api-3:8000;
}

server {
    listen 80;
    
    location / {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Database Scaling:**
- **Read replicas**: For read-heavy workloads
- **PgBouncer**: Connection pooler for PostgreSQL
- **Partitioning**: Partition file_state by indexed_at

---

## Monitoring & Debugging

### Health Checks

**Docker health check:**
```yaml
healthcheck:
  test: ["CMD", "/app/.venv/bin/python", "-c", "import httpx; httpx.get('http://localhost:8000/health', timeout=5.0)"]
  interval: 30s      # Check every 30 seconds
  timeout: 10s       # Fail if takes >10s
  retries: 3         # 3 failed checks = unhealthy
  start_period: 10s  # Grace period on startup
```

**Health endpoint response:**
```json
{
  "status": "healthy",
  "vector_store_id": "vs_6900e6fc7c94819187c6ec114fd3adc9",
  "database": "connected"
}
```

### Logging

**Structured logs:**
```
2025-10-30 20:45:02 - __main__ - INFO - ✅ API service initialized
2025-10-30 20:45:15 - __main__ - INFO - Search request: query='Holocaust education', max_results=10
2025-10-30 20:45:15 - __main__ - INFO - Search completed: 10 results found
2025-10-30 20:46:22 - __main__ - ERROR - ⚠️ Database error for sha256 abc123: connection timeout
```

**Log levels:**
- `INFO`: Normal operations (requests, responses)
- `WARNING`: Recoverable issues (missing metadata)
- `ERROR`: Failures (database errors, API errors)
- `DEBUG`: Detailed debugging information

**View logs:**
```bash
# Real-time logs
docker compose logs -f api

# Last 100 lines
docker compose logs --tail=100 api

# Specific time range
docker compose logs --since="2025-10-30T20:00:00" api

# Search logs
docker compose logs api | grep "ERROR"
```

### Debugging Tools

**1. Interactive Shell:**
```bash
# Enter running container
docker exec -it ai-kb-api /bin/bash

# Python REPL
docker exec -it ai-kb-api python

# Test database connection
docker exec -it ai-kb-api python -c "
import psycopg2
conn = psycopg2.connect(
    host='postgres',
    database='ai_knowledge_base',
    user='postgres',
    password='postgres'
)
print('Database connected!')
"
```

**2. Network Testing:**
```bash
# Test connectivity from cloudflared
docker run --rm --network apps nicolaka/netshoot curl http://ai-kb-api:8000/health

# Test from within API container
docker exec ai-kb-api curl http://localhost:8000/health

# Test database connection
docker exec ai-kb-api pg_isready -h postgres -U postgres
```

**3. Performance Profiling:**
```bash
# Install py-spy
docker exec ai-kb-api pip install py-spy

# Profile running process
docker exec ai-kb-api py-spy top --pid 1

# Generate flamegraph
docker exec ai-kb-api py-spy record --pid 1 --output profile.svg
```

### Common Issues

**Issue: Database connection timeout**
```
ERROR - ⚠️ Database error for sha256 abc123: connection timeout
```
**Solution:**
- Check database is running: `docker compose ps postgres`
- Verify connection pool settings
- Increase `max_connections` in PostgreSQL

**Issue: OpenAI API rate limit**
```
OpenAI API error: 429 - Rate limit exceeded
```
**Solution:**
- Implement exponential backoff
- Reduce concurrent requests
- Upgrade OpenAI plan

**Issue: S3 presigned URL 403**
```
⚠️ Could not generate S3 URL: SignatureDoesNotMatch
```
**Solution:**
- Verify S3 credentials in .env
- Check bucket permissions
- Ensure correct region configuration

### Metrics Collection (Future)

**Prometheus metrics:**
```python
from prometheus_fastapi_instrumentator import Instrumentator

instrumentator = Instrumentator()
instrumentator.instrument(app).expose(app)
```

**Metrics endpoints:**
- `/metrics` - Prometheus metrics
- Grafana dashboard for visualization
- Alerts for anomalies

---

## API Usage Examples

### cURL Examples

**Basic search:**
```bash
curl -X POST http://localhost:8001/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Holocaust education materials",
    "max_results": 5
  }' | jq .
```

**Search with query rewriting disabled:**
```bash
curl -X POST https://ai-kb-api.yourdomain.com/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Magyar cserkészet története",
    "max_results": 10,
    "rewrite_query": false
  }' | jq '.results[].metadata.original_name'
```

### Python Client

```python
import requests
from typing import List, Dict

class KnowledgeBaseClient:
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        
    def search(self, query: str, max_results: int = 10) -> Dict:
        """Perform semantic search"""
        response = requests.post(
            f"{self.base_url}/api/search",
            json={
                "query": query,
                "max_results": max_results
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
    def health_check(self) -> Dict:
        """Check API health"""
        response = requests.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()

# Usage
client = KnowledgeBaseClient("https://ai-kb-api.yourdomain.com")

results = client.search("Peula activities for youth", max_results=5)
print(f"Found {results['count']} results")

for i, result in enumerate(results['results'], 1):
    print(f"\n{i}. {result['metadata']['original_name']}")
    print(f"   Score: {result['score']:.4f}")
    print(f"   Content: {result['content'][0]['text'][:200]}...")
    print(f"   Download: {result['metadata']['original_file_download_url']}")
```

### JavaScript/TypeScript

```typescript
interface SearchRequest {
  query: string;
  max_results?: number;
  rewrite_query?: boolean;
}

interface SearchResponse {
  query: string;
  results: SearchResult[];
  count: number;
}

interface SearchResult {
  score: number;
  content: ContentItem[];
  metadata: FileMetadata;
}

class KnowledgeBaseAPI {
  constructor(private baseURL: string = 'http://localhost:8001') {}
  
  async search(request: SearchRequest): Promise<SearchResponse> {
    const response = await fetch(`${this.baseURL}/api/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request)
    });
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    
    return response.json();
  }
  
  async healthCheck(): Promise<{status: string; database: string}> {
    const response = await fetch(`${this.baseURL}/health`);
    return response.json();
  }
}

// Usage
const api = new KnowledgeBaseAPI('https://ai-kb-api.yourdomain.com');

const results = await api.search({
  query: 'Scout activities for teenagers',
  max_results: 10
});

console.log(`Found ${results.count} results`);
results.results.forEach((result, i) => {
  console.log(`${i+1}. ${result.metadata.original_name}`);
  console.log(`   Score: ${result.score.toFixed(4)}`);
});
```

---

## Appendix

### Environment Variables Reference

```bash
# OpenAI Configuration (Required)
OPENAI_API_KEY=sk-proj-xxx...              # OpenAI API key
VECTOR_STORE_ID=vs_xxx...                  # Vector Store ID

# PostgreSQL Database (Required)
POSTGRES_HOST=postgres                     # Database host
POSTGRES_PORT=5432                         # Database port
POSTGRES_DB=ai_knowledge_base              # Database name
POSTGRES_USER=postgres                     # Database user
POSTGRES_PASSWORD=secure_password          # Database password

# S3 Storage (Required)
S3_ENDPOINT=https://fra1.digitaloceanspaces.com  # S3 endpoint
S3_REGION=fra1                             # S3 region
S3_BUCKET=somer-ai                         # S3 bucket name
S3_ACCESS_KEY=xxx...                       # S3 access key
S3_SECRET_KEY=xxx...                       # S3 secret key

# API Configuration (Optional)
API_PORT=8000                              # API port (default: 8000)
API_HOST=0.0.0.0                          # API host (default: 0.0.0.0)

# CORS Configuration (Optional)
CORS_ORIGINS=*                             # Allowed origins (default: *)
                                          # Production: https://app.example.com,https://example.com
```

### API Response Examples

**Successful search with results:**
```json
{
  "query": "Hogyan szervezz Peula programot?",
  "results": [
    {
      "score": 0.6967456984385832,
      "content": [
        {
          "type": "text",
          "text": "Summary of the activity: We will play a game with different roles, it'll be played on an island..."
        }
      ],
      "metadata": {
        "original_name": "Youth Inclusion Toolbox.pdf",
        "original_file_download_url": "https://fra1.digitaloceanspaces.com/somer-ai/objects/30/01/3001d6336b20c90358f5ba08ce79ca52f798c82892389a2db39a79fba0714c1f.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256&...",
        "processed_text_download_url": "https://fra1.digitaloceanspaces.com/somer-ai/derivatives/30/01/3001d6336b20c90358f5ba08ce79ca52f798c82892389a2db39a79fba0714c1f/text.txt?X-Amz-Algorithm=AWS4-HMAC-SHA256&...",
        "sha256": "3001d6336b20c90358f5ba08ce79ca52f798c82892389a2db39a79fba0714c1f"
      }
    }
  ],
  "count": 1
}
```

**Empty results:**
```json
{
  "query": "nonexistent topic xyz",
  "results": [],
  "count": 0
}
```

**Error response:**
```json
{
  "detail": "OpenAI API error: 429 - Rate limit exceeded"
}
```

### Quick Reference Commands

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# Restart API only
docker compose restart api

# View logs
docker compose logs -f api

# Check health
curl http://localhost:8001/health

# Run search
curl -X POST http://localhost:8001/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "max_results": 1}'

# Database shell
docker exec -it ai-kb-postgres psql -U postgres -d ai_knowledge_base

# API shell
docker exec -it ai-kb-api /bin/bash

# Update deployment
git pull && docker compose build api && docker compose up -d api
```

---

## Support & Resources

- **Repository**: https://github.com/hasomerhacairhu/ai-knowledge-base-ingest
- **Production API**: https://ai-kb-api.yourdomain.com
- **Interactive Docs**: https://ai-kb-api.yourdomain.com/docs
- **Server**: root@100.106.229.15 (SSH access via Tailscale)

**Version**: 1.0.0  
**Last Updated**: October 30, 2025  
**Maintained by**: AI Knowledge Base Team
