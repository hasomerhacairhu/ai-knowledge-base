# API Reference - Direct Vector Store Search

## Overview

This folder contains the reference implementation for querying the OpenAI vector store **without using an LLM**. This is the recommended approach for building your Custom GPT API, as it provides:

- ⚡ **5x faster** than LLM-based methods (2.3s vs 11-12s)
- 💰 **Fixed cost**: $2.50 per 1,000 searches (vs variable token costs)
- 🎯 **Pure semantic search** with relevance scores
- 📊 **Raw document chunks** for custom processing
- 🔗 **Full metadata**: Drive URLs, S3 presigned URLs, filenames

## Architecture

```
┌─────────────────┐
│   Your API      │
│  (FastAPI, etc) │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  direct_search.py                   │
│  ┌─────────────────────────────┐   │
│  │ 1. Vector Store Search API  │   │
│  │    (OpenAI undocumented)    │   │
│  └──────────┬──────────────────┘   │
│             ▼                       │
│  ┌─────────────────────────────┐   │
│  │ 2. Database Enrichment      │   │
│  │    - SHA256 → metadata      │   │
│  │    - Drive URLs             │   │
│  │    - S3 presigned URLs      │   │
│  └──────────┬──────────────────┘   │
│             ▼                       │
│  ┌─────────────────────────────┐   │
│  │ 3. Return enriched results  │   │
│  │    with full provenance     │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  Custom GPT     │
│  (OpenAI)       │
└─────────────────┘
```

## Quick Start

### Prerequisites

```bash
# Environment variables needed
OPENAI_API_KEY=sk-proj-...
VECTOR_STORE_ID=vs_...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-bucket
```

### Basic Usage

```bash
# Simple search
python direct_search.py "What is Centropa?"

# Show full content (no truncation)
python direct_search.py "Ki volt Koltai István?" --full

# Custom preview length
python direct_search.py "Holocaust education" --preview-length 1000

# More results
python direct_search.py "Kindertransport" --max-results 20
```

### Response Format

```json
{
  "results": [
    {
      "content": "Full document chunk text...",
      "relevance_score": 0.8956,
      "file_id": "file-abc123",
      "filename": "koltai-istvan_interjureszlet.docx",
      "drive_url": "https://drive.google.com/file/d/1ABC.../view",
      "s3_presigned_url": "https://s3.amazonaws.com/bucket/objects/4f/0d/...?X-Amz-Signature=...",
      "s3_key": "objects/4f/0d/4f0df2fa...docx",
      "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }
  ],
  "query": "Ki volt Koltai István?",
  "total_results": 10
}
```

## Integration Guide

### Option 1: Direct Function Call

```python
from direct_search import vector_store_search, get_file_metadata

# Perform search
results = vector_store_search("Your query", max_results=10)

# Enrich with metadata
for result in results:
    sha256 = result["file_id"].replace("file-", "").split(".")[0]
    metadata = get_file_metadata(sha256)
    
    if metadata:
        result["filename"] = metadata["filename"]
        result["drive_url"] = metadata["drive_url"]
        result["s3_presigned_url"] = metadata["s3_presigned_url"]
        # ... use enriched result
```

### Option 2: HTTP Wrapper (Recommended for API)

```python
from fastapi import FastAPI, Query
from direct_search import vector_store_search, get_file_metadata

app = FastAPI()

@app.get("/search")
async def search(
    q: str = Query(..., description="Search query"),
    max_results: int = Query(10, ge=1, le=50)
):
    """
    Semantic search endpoint for Custom GPT
    """
    # Perform vector store search
    raw_results = vector_store_search(q, max_results)
    
    # Enrich with metadata
    enriched_results = []
    for result in raw_results:
        # Extract SHA256 from OpenAI file_id
        sha256 = extract_sha256(result["file_id"])
        metadata = get_file_metadata(sha256)
        
        enriched_results.append({
            "content": result["content"],
            "relevance": result["score"],
            "source": {
                "filename": metadata["filename"],
                "drive_url": metadata["drive_url"],
                "s3_url": metadata["s3_presigned_url"]
            }
        })
    
    return {
        "query": q,
        "results": enriched_results
    }
```

### Option 3: Subprocess Call

```python
import subprocess
import json

def search_knowledge_base(query: str, max_results: int = 10):
    """
    Call direct_search.py as subprocess
    """
    cmd = [
        "python", "direct_search.py",
        query,
        "--max-results", str(max_results),
        "--full"
    ]
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )
    
    # Parse output and return structured data
    return parse_search_output(result.stdout)
```

## Key Features

### 1. Vector Store Search API

The core innovation is using OpenAI's undocumented Vector Store Search API:

```python
endpoint = f"https://api.openai.com/v1/vector_stores/{vector_store_id}/search"

response = httpx.post(
    endpoint,
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "OpenAI-Beta": "assistants=v2"
    },
    json={
        "query": "Your search query",
        "limit": 10
    }
)
```

**Benefits:**
- No LLM involved = no token costs
- Fixed pricing: $2.50 per 1,000 searches
- Returns raw chunks with relevance scores
- Perfect for custom processing

### 2. Database Metadata Enrichment

```python
def get_file_metadata(sha256: str) -> Optional[Dict[str, Any]]:
    """
    Queries pipeline.db to get:
    - Original filename from Google Drive
    - S3 key
    - Drive file ID
    - MIME type
    - File paths
    
    Then generates:
    - Google Drive URL
    - S3 presigned URL (valid 1 hour)
    """
```

**Database Schema:**

```sql
-- file_state table
SELECT 
    s3_key,
    original_name,
    mime_type,
    sha256,
    openai_file_id
FROM file_state
WHERE sha256 = ?

-- drive_file_mapping table
SELECT 
    drive_file_id,
    drive_file_name,
    drive_parent_path
FROM drive_file_mapping
WHERE sha256 = ?
```

### 3. S3 Presigned URLs

```python
s3_client = boto3.client(
    's3',
    region_name=os.getenv('AWS_REGION', 'us-east-1'),
    config=Config(signature_version='s3v4')
)

presigned_url = s3_client.generate_presigned_url(
    'get_object',
    Params={'Bucket': bucket_name, 'Key': s3_key},
    ExpiresIn=3600  # 1 hour
)
```

## Performance Metrics

Based on comprehensive testing (see `QUERY_TEST_ANALYSIS.md`):

| Metric | Direct Search | LLM Methods |
|--------|--------------|-------------|
| **Avg Response Time** | 2.43s | 11-12s |
| **Cost** | $2.50/1k searches | ~$0.0015/query |
| **Success Rate** | 100% | 100% |
| **Avg Relevance** | 0.68-0.70 | N/A (synthesized) |
| **Multilingual** | ✅ Perfect | ✅ Perfect |

**Key Advantages:**
- 5x faster response times
- Predictable, low-cost pricing model
- Raw chunks for custom LLM processing
- No token usage variability

## Content Verification

All content has been verified for accuracy (see `CONTENT_VERIFICATION_REPORT.md`):

- ✅ 100% pass rate (36/36 checks)
- ✅ OpenAI files match database records
- ✅ Filenames consistent across systems
- ✅ Drive URLs valid and accessible
- ✅ S3 URLs contain correct SHA256
- ✅ Multilingual content (Hungarian + English) perfect

## API Implementation Checklist

When building your Custom GPT API:

- [ ] Set up environment variables (OpenAI, AWS, Vector Store ID)
- [ ] Copy `direct_search.py` to your API project
- [ ] Set up database connection to `pipeline.db`
- [ ] Implement HTTP endpoint (FastAPI, Flask, etc.)
- [ ] Add authentication/rate limiting
- [ ] Test with multilingual queries
- [ ] Implement error handling
- [ ] Add logging/monitoring
- [ ] Configure CORS for Custom GPT
- [ ] Deploy with Docker (optional)

## Example API Endpoint

```python
# app.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from direct_search import vector_store_search, get_file_metadata
import logging

app = FastAPI(title="Knowledge Base API")
logging.basicConfig(level=logging.INFO)

class SearchRequest(BaseModel):
    query: str
    max_results: int = 10
    preview_length: int = 500
    show_full: bool = False

class SearchResponse(BaseModel):
    query: str
    results: list
    total_results: int

@app.post("/api/v1/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Semantic search endpoint for Custom GPT
    
    Args:
        query: Search query (any language)
        max_results: Number of results (1-50)
        preview_length: Content preview length
        show_full: Return full content without truncation
    
    Returns:
        Enriched search results with Drive URLs and S3 URLs
    """
    try:
        # Perform vector store search
        results = vector_store_search(
            request.query,
            max_results=request.max_results
        )
        
        # Enrich with metadata
        enriched = []
        for result in results:
            sha256 = extract_sha256_from_file_id(result["file_id"])
            metadata = get_file_metadata(sha256)
            
            content = result["content"]
            if not request.show_full and request.preview_length > 0:
                content = content[:request.preview_length]
            
            enriched.append({
                "content": content,
                "relevance_score": result["score"],
                "filename": metadata.get("filename"),
                "drive_url": metadata.get("drive_url"),
                "s3_url": metadata.get("s3_presigned_url"),
                "mime_type": metadata.get("mime_type")
            })
        
        return SearchResponse(
            query=request.query,
            results=enriched,
            total_results=len(enriched)
        )
        
    except Exception as e:
        logging.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Run with: uvicorn app:app --reload
```

## Testing

```bash
# Test the search
python direct_search.py "What is Centropa?"

# Test with full content
python direct_search.py "Ki volt Koltai István?" --full

# Test API endpoint (if implemented)
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Holocaust education", "max_results": 10}'
```

## Documentation

This folder includes comprehensive documentation:

1. **QUERY_IMPROVEMENTS.md** - Comparison of three query methods
2. **SPEED_COMPARISON.md** - Performance benchmarks (5x faster)
3. **CONTENT_QUALITY_ANALYSIS.md** - LLM synthesis vs raw chunks
4. **CONTENT_VERIFICATION_REPORT.md** - 100% accuracy verification
5. **QUERY_TEST_ANALYSIS.md** - Test results across 18 queries

## Support & Troubleshooting

### Common Issues

**Issue**: "Vector store not found"
```python
# Solution: Check VECTOR_STORE_ID in .env
VECTOR_STORE_ID=vs_abc123...
```

**Issue**: "Database not found"
```python
# Solution: Update DB_PATH in direct_search.py
DB_PATH = "/absolute/path/to/pipeline.db"
```

**Issue**: "S3 presigned URL expired"
```python
# Solution: URLs are valid for 1 hour, regenerate on each request
# The get_file_metadata() function creates fresh URLs
```

**Issue**: "Encoding error with Hungarian text"
```python
# Solution: Ensure UTF-8 encoding throughout
# Already handled in direct_search.py
```

## Next Steps

1. **Create your API project**: FastAPI, Flask, or Express
2. **Copy direct_search.py**: Adapt to your framework
3. **Set up database access**: Point to your pipeline.db
4. **Implement authentication**: Protect your endpoints
5. **Deploy**: Docker, AWS Lambda, Cloud Run, etc.
6. **Connect Custom GPT**: Configure action with your API endpoint

## Contact & Support

For questions about the ingest pipeline, refer to the main repository README.
For API implementation help, review the documentation in this folder.
