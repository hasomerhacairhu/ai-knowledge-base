# Knowledge Base Search API

FastAPI service providing semantic search over an OpenAI Vector Store with enriched file metadata.

## Overview

This API exposes a search endpoint that:
- Queries OpenAI Vector Store directly (no LLM inference)
- Returns relevant document chunks with confidence scores
- Enriches results with file metadata from PostgreSQL
- Generates presigned S3 URLs (7-day expiration) for:
  - Original documents (PDF, DOCX, etc.)
  - Processed text files (.txt)
- Includes file sizes and provenance information

## Base URL

```
http://localhost:8000
```

## Endpoints

### POST `/api/search`

Semantic search with detailed results and metadata enrichment.

**Request Body:**

```json
{
  "query": "Your search query",
  "max_results": 10,
  "rewrite_query": true
}
```

**Parameters:**
- `query` (string, required): Search query text
- `max_results` (integer, optional): Number of results to return (default: 10, max: 50)
- `rewrite_query` (boolean, optional): Whether to optimize query for vector search (default: true)

**Response:**

```json
{
  "query": "Your search query",
  "search_query": "Optimized query used for vector search",
  "results": [
    {
      "filename": "document_hash.pdf",
      "file_id": "file-abc123",
      "score": 0.8542,
      "content": [
        {
          "type": "text",
          "text": "Relevant paragraph from the document..."
        }
      ],
      "attributes": {
        "start_index": 1024,
        "end_index": 2048
      },
      "metadata": {
        "original_name": "Important Document.pdf",
        "drive_path": "/Shared Drive/Folder/Important Document.pdf",
        "mime_type": "application/pdf",
        "drive_file_id": "1abc123xyz",
        "drive_url": "https://drive.google.com/file/d/1abc123xyz/view",
        "s3_key": "documents/important_document.pdf",
        "s3_presigned_url": "https://s3.amazonaws.com/...",
        "txt_file_url": "https://s3.amazonaws.com/...",
        "file_size_bytes": 2457600,
        "txt_size_bytes": 45120,
        "sha256": "abc123def456..."
      }
    }
  ],
  "count": 1
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `query` | string | Original search query |
| `search_query` | string | Optimized query used for vector search (may differ from original) |
| `results` | array | List of search results ordered by relevance |
| `count` | integer | Number of results returned |

**Search Result Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `filename` | string | OpenAI Vector Store filename (hash-based) |
| `file_id` | string | OpenAI file ID |
| `score` | float | Confidence/relevance score (0.0-1.0, higher is more relevant) |
| `content` | array | List of content items (paragraph quotes) |
| `attributes` | object | Chunk metadata (start/end indices) |
| `metadata` | object | Enriched file metadata (see below) |

**File Metadata Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `original_name` | string | Original filename from Google Drive |
| `drive_path` | string | Full path in Google Drive |
| `mime_type` | string | MIME type (application/pdf, etc.) |
| `drive_file_id` | string | Google Drive file ID |
| `drive_url` | string | Direct link to view file in Google Drive |
| `s3_key` | string | S3 object key |
| `s3_presigned_url` | string | Presigned URL for original file (7-day expiration) |
| `txt_file_url` | string | Presigned URL for processed text file (7-day expiration) |
| `file_size_bytes` | integer | Original file size in bytes |
| `txt_size_bytes` | integer | Processed text file size in bytes |
| `sha256` | string | SHA256 hash of the file |

### GET `/api/search`

Convenience endpoint for simple queries via URL parameters.

**Query Parameters:**
- `q` (string, required): Search query text
- `max_results` (integer, optional): Number of results (default: 10)

**Example:**
```
GET /api/search?q=What%20is%20Centropa&max_results=5
```

**Response:** Same format as POST endpoint

### GET `/`

Root endpoint returning API information.

**Response:**
```json
{
  "message": "Knowledge Base Search API",
  "version": "1.0.0",
  "endpoints": {
    "search": "/api/search",
    "health": "/api/health",
    "docs": "/docs"
  }
}
```

### GET `/api/health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "vector_store_id": "vs_abc123",
  "database": "connected"
}
```

### GET `/docs`

Interactive API documentation (Swagger UI).

### GET `/redoc`

Alternative API documentation (ReDoc).

## Usage Examples

### cURL

**Basic search:**
```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is Centropa?",
    "max_results": 5
  }'
```

**Search with query rewriting disabled:**
```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Ki volt Koltai Anna?",
    "max_results": 10,
    "rewrite_query": false
  }'
```

**GET request:**
```bash
curl "http://localhost:8000/api/search?q=What%20is%20Centropa&max_results=5"
```

**Health check:**
```bash
curl http://localhost:8000/api/health
```

### Python

```python
import requests

# Search request
response = requests.post(
    "http://localhost:8000/api/search",
    json={
        "query": "What is Centropa?",
        "max_results": 5
    }
)

results = response.json()
print(f"Found {results['count']} results")

for result in results['results']:
    print(f"\nFilename: {result['metadata']['original_name']}")
    print(f"Score: {result['score']:.4f}")
    print(f"Content: {result['content'][0]['text'][:200]}...")
    print(f"Drive URL: {result['metadata']['drive_url']}")
    print(f"S3 URL (7 days): {result['metadata']['s3_presigned_url']}")
    print(f"Processed txt URL (7 days): {result['metadata']['txt_file_url']}")
    print(f"File size: {result['metadata']['file_size_bytes']} bytes")
```

### JavaScript (Node.js)

```javascript
const axios = require('axios');

async function search(query, maxResults = 10) {
  try {
    const response = await axios.post('http://localhost:8000/api/search', {
      query: query,
      max_results: maxResults
    });

    const { results, count } = response.data;
    console.log(`Found ${count} results`);

    results.forEach((result, idx) => {
      console.log(`\n${idx + 1}. ${result.metadata.original_name}`);
      console.log(`   Score: ${result.score.toFixed(4)}`);
      console.log(`   Content: ${result.content[0].text.substring(0, 200)}...`);
      console.log(`   Drive URL: ${result.metadata.drive_url}`);
      console.log(`   S3 URL (7 days): ${result.metadata.s3_presigned_url}`);
      console.log(`   Processed txt URL (7 days): ${result.metadata.txt_file_url}`);
      console.log(`   File size: ${result.metadata.file_size_bytes} bytes`);
    });
  } catch (error) {
    console.error('Search error:', error.message);
  }
}

search("What is Centropa?", 5);
```

### JavaScript (Browser / Fetch API)

```javascript
async function searchKnowledgeBase(query, maxResults = 10) {
  try {
    const response = await fetch('http://localhost:8000/api/search', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query: query,
        max_results: maxResults
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    console.log(`Found ${data.count} results`);

    data.results.forEach((result, idx) => {
      console.log(`\n${idx + 1}. ${result.metadata.original_name}`);
      console.log(`   Score: ${result.score.toFixed(4)}`);
      console.log(`   Drive: ${result.metadata.drive_url}`);
      console.log(`   S3 Original (7d): ${result.metadata.s3_presigned_url}`);
      console.log(`   S3 Text (7d): ${result.metadata.txt_file_url}`);
    });

    return data;
  } catch (error) {
    console.error('Search failed:', error);
  }
}

// Usage
searchKnowledgeBase("What is Centropa?", 5);
```

## Architecture

### Data Flow

1. **Request**: Client sends search query to `/api/search`
2. **Vector Search**: API queries OpenAI Vector Store directly (no LLM)
3. **Results**: OpenAI returns document chunks with relevance scores
4. **Enrichment**: API queries PostgreSQL for file metadata
5. **S3 URLs**: Generate presigned URLs for original and processed files (7-day expiration)
6. **Response**: Return enriched results with all metadata

### Components

- **FastAPI**: Web framework with automatic OpenAPI documentation
- **OpenAI Vector Store**: Semantic search over embedded documents
- **PostgreSQL**: File metadata and provenance tracking
- **S3**: Object storage for original and processed documents
- **httpx**: Async HTTP client for OpenAI API calls

### Database Schema

**file_state table:**
```sql
CREATE TABLE file_state (
    sha256 TEXT PRIMARY KEY,
    s3_key TEXT NOT NULL,
    original_name TEXT,
    status TEXT NOT NULL,
    synced_at TIMESTAMP,
    processed_at TIMESTAMP,
    indexed_at TIMESTAMP,
    openai_file_id TEXT,
    size_bytes BIGINT,
    error_message TEXT
);
```

**drive_file_mapping table:**
```sql
CREATE TABLE drive_file_mapping (
    sha256 TEXT PRIMARY KEY,
    drive_file_id TEXT NOT NULL,
    drive_file_name TEXT NOT NULL,
    drive_parent_path TEXT,
    drive_modified_time TIMESTAMP,
    drive_mime_type TEXT
);
```

## Configuration

Required environment variables (`.env`):

```bash
# OpenAI Configuration
OPENAI_API_KEY=sk-...
VECTOR_STORE_ID=vs_...

# PostgreSQL Database (Required)
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=ai_knowledge_base
POSTGRES_USER=postgres
POSTGRES_PASSWORD=secure_password

# S3 Storage
S3_ENDPOINT=https://s3.amazonaws.com
S3_REGION=us-east-1
S3_BUCKET=knowledge-base-docs
S3_ACCESS_KEY=...
S3_SECRET_KEY=...

# API Configuration
API_PORT=8000
API_HOST=0.0.0.0

# CORS Configuration (Optional, comma-separated origins)
# For production, specify allowed origins: https://example.com,https://app.example.com
CORS_ORIGINS=*
```

## Running the API

### Docker Compose (Recommended)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down
```

### Local Development

```bash
# Install dependencies
cd services/api
uv sync

# Run with uvicorn
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Access Points

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health Check: http://localhost:8000/api/health

## Technical Details

### Direct Vector Store Search

This API uses OpenAI's Vector Store Search endpoint directly, bypassing LLM generation:

- **Endpoint**: `POST https://api.openai.com/v1/vector_stores/{id}/search`
- **Cost**: Fixed $2.50 per 1,000 searches (no token costs)
- **Response Time**: Instant (no LLM overhead)
- **Returns**: Raw document chunks with relevance scores

### Query Rewriting

When `rewrite_query=true` (default), OpenAI optimizes the query for better vector search results. The optimized query is returned in `search_query` field.

### S3 Presigned URLs

Generated URLs expire after 7 days (604,800 seconds). Two URLs are provided:

1. **s3_presigned_url**: Original file (PDF, DOCX, etc.)
2. **txt_file_url**: Processed text file extracted by Docling

### Confidence Scores

Search results include a `score` field (0.0-1.0) indicating semantic similarity:

- **0.8-1.0**: High confidence, very relevant
- **0.6-0.8**: Medium confidence, relevant
- **0.4-0.6**: Lower confidence, potentially relevant
- **<0.4**: Low confidence, may not be relevant

## Error Handling

### 400 Bad Request

Query parameter is required:
```json
{
  "detail": "Query parameter is required"
}
```

### 404 Not Found

File metadata not found (file may not be synced):
```json
{
  "metadata": null
}
```

### 500 Internal Server Error

OpenAI API or database errors:
```json
{
  "detail": "Internal server error"
}
```

### 503 Service Unavailable

Vector Store or database not available:
```json
{
  "detail": "Service temporarily unavailable"
}
```

## Performance

- **Search latency**: <500ms (vector search only, no LLM)
- **Throughput**: >100 requests/second
- **Database queries**: 1 query per result (metadata enrichment)
- **S3 presigned URLs**: Generated on-demand (cached by client)

## Reference Implementation

See `api-reference/direct_search.py` for a standalone example of:
- Direct vector store search
- Database metadata enrichment
- S3 presigned URL generation
- Result formatting and display
