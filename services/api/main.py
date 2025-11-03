#!/usr/bin/env python3
"""
AI Knowledge Base API Service
FastAPI service for semantic search over the vector store
"""

import os
import sys
import logging
import json
import hashlib
import psycopg2
from psycopg2 import pool
import boto3
import redis
from typing import Dict, List, Optional, Any, Union
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
import httpx
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# Request/Response Models
class SearchRequest(BaseModel):
    query: Union[str, List[str]] = Field(..., description="Search query or list of queries")
    rewrite_query: bool = Field(True, description="Whether to rewrite the query for better search results")


class ContentItem(BaseModel):
    type: str
    text: str


class FileMetadata(BaseModel):
    original_name: str
    original_file_url: str
    processed_text_url: Optional[str] = None
    sha256: str


class SearchResult(BaseModel):
    score: float
    content: List[ContentItem]
    metadata: Optional[FileMetadata] = None


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    count: int
    total: Optional[int] = None
    page: Optional[int] = None
    page_size: Optional[int] = None
    has_more: Optional[bool] = None


# Global clients
s3_client = None
openai_headers = None
vector_store_id = None
db_pool = None
redis_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize clients on startup"""
    global s3_client, openai_headers, vector_store_id, db_pool, redis_client
    
    # Initialize S3 client
    s3_region = os.getenv("S3_REGION", "us-east-1")
    config = Config(
        signature_version='s3v4',
        retries={'max_attempts': 3, 'mode': 'adaptive'}
    )
    
    s3_client = boto3.client(
        's3',
        region_name=s3_region,
        endpoint_url=os.getenv("S3_ENDPOINT"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
        config=config
    )
    
    # Initialize OpenAI headers
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    
    openai_headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    # Get vector store ID
    vector_store_id = os.getenv("VECTOR_STORE_ID")
    if not vector_store_id:
        raise ValueError("VECTOR_STORE_ID not set")
    
    # Initialize PostgreSQL connection pool
    try:
        db_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            host=os.getenv("POSTGRES_HOST", "postgres"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "ai_knowledge_base"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres")
        )
        logger.info("✅ PostgreSQL connection pool initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize PostgreSQL connection pool: {e}")
        raise ValueError(f"Failed to initialize PostgreSQL connection pool: {e}")
    
    # Initialize Redis client
    try:
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=0,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        # Test connection
        redis_client.ping()
        logger.info("✅ Redis cache initialized")
    except Exception as e:
        logger.warning(f"⚠️  Redis not available, caching disabled: {e}")
        redis_client = None
    
    logger.info("✅ API service initialized")
    yield
    
    # Cleanup
    if db_pool:
        db_pool.closeall()
        logger.info("🛑 PostgreSQL connection pool closed")
    if redis_client:
        redis_client.close()
        logger.info("🛑 Redis connection closed")
    logger.info("🛑 API service shutting down")


# Initialize FastAPI app
app = FastAPI(
    title="AI Knowledge Base API",
    description="Semantic search API for AI Knowledge Base using OpenAI Vector Store",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_file_metadata(sha256_hash: str, base_url: str) -> Optional[FileMetadata]:
    """
    Look up file metadata from PostgreSQL database by SHA256 hash.
    
    Args:
        sha256_hash: SHA256 hash extracted from OpenAI filename
        base_url: Base URL for file proxies
        
    Returns:
        FileMetadata object or None with short proxy URLs
    """
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                dfm.original_name,
                fs.s3_key,
                fs.sha256
            FROM drive_file_mapping dfm
            JOIN file_state fs ON dfm.sha256 = fs.sha256
            WHERE fs.sha256 = %s
            LIMIT 1
        ''', (sha256_hash,))
        
        result = cursor.fetchone()
        
        if result:
            original_name, s3_key, sha256 = result
            
            # Generate short proxy URLs instead of presigned S3 URLs
            original_file_url = f"{base_url}/file/{sha256}"
            processed_text_url = f"{base_url}/text/{sha256}"
            
            return FileMetadata(
                original_name=original_name,
                original_file_url=original_file_url,
                processed_text_url=processed_text_url,
                sha256=sha256
            )
        
        return None
        
    except Exception as e:
        logger.error(f"⚠️  Database error for sha256 {sha256_hash}: {e}")
        return None
    finally:
        if conn:
            db_pool.putconn(conn)


def generate_presigned_url(sha256: str, file_type: str = "original") -> Optional[str]:
    """
    Generate presigned S3 URL for file download
    
    Args:
        sha256: File SHA256 hash
        file_type: "original" or "text"
        
    Returns:
        Presigned URL or None
    """
    conn = None
    try:
        logger.info(f"Generating presigned URL for {sha256[:16]}... (type: {file_type})")
        conn = db_pool.getconn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT s3_key FROM file_state WHERE sha256 = %s LIMIT 1
        ''', (sha256,))
        
        result = cursor.fetchone()
        logger.info(f"Database query result for {sha256[:16]}...: {result}")
        
        if result:
            s3_key = result[0]
            
            if file_type == "text":
                # Text files are stored as: derivatives/{shard1}/{shard2}/{sha256}/text.txt
                shard1 = sha256[:2]
                shard2 = sha256[2:4]
                s3_key = f"derivatives/{shard1}/{shard2}/{sha256}/text.txt"
            
            logger.info(f"Using S3 key: {s3_key}")
            
            # Generate presigned URL (7 days = 604800 seconds)
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': os.getenv("S3_BUCKET"),
                    'Key': s3_key
                },
                ExpiresIn=604800
            )
            logger.info(f"✓ Generated presigned URL for {sha256[:16]}...")
            return url
        
        logger.warning(f"No database record found for {sha256[:16]}...")
        return None
        
    except Exception as e:
        logger.error(f"⚠️  Error generating presigned URL for {sha256[:16]}...: {e}")
        return None
    finally:
        if conn:
            db_pool.putconn(conn)


def get_cache_key(query: str, max_num_results: int, rewrite_query: bool) -> str:
    """
    Generate cache key for search query
    
    Args:
        query: Search query
        max_num_results: Number of results
        rewrite_query: Query rewrite flag
        
    Returns:
        Cache key string
    """
    # Create deterministic key from query parameters
    params = f"{query}|{max_num_results}|{rewrite_query}"
    key_hash = hashlib.sha256(params.encode()).hexdigest()[:16]
    return f"search:{key_hash}"


def get_cached_results(cache_key: str) -> Optional[Dict[str, Any]]:
    """
    Get cached search results from Redis
    
    Args:
        cache_key: Cache key
        
    Returns:
        Cached results or None
    """
    if not redis_client:
        return None
    
    try:
        cached = redis_client.get(cache_key)
        if cached:
            logger.info(f"✓ Cache HIT: {cache_key}")
            return json.loads(cached)
    except Exception as e:
        logger.warning(f"Cache read error: {e}")
    
    return None


def set_cached_results(cache_key: str, results: Dict[str, Any], ttl: int = None):
    """
    Store search results in Redis cache
    
    Args:
        cache_key: Cache key
        results: Search results to cache
        ttl: Time to live in seconds (default from env)
    """
    if not redis_client:
        return
    
    try:
        if ttl is None:
            ttl = int(os.getenv("CACHE_TTL", "3600"))  # Default 1 hour
        
        redis_client.setex(
            cache_key,
            ttl,
            json.dumps(results)
        )
        logger.info(f"✓ Cached: {cache_key} (TTL: {ttl}s)")
    except Exception as e:
        logger.warning(f"Cache write error: {e}")


async def vector_store_search(
    query: str,
    max_num_results: int = 10,
    rewrite_query: bool = True
) -> Dict[str, Any]:
    """
    Direct search of vector store with caching.
    
    Args:
        query: Search query
        max_num_results: Number of results to return (1-50)
        rewrite_query: Whether to optimize query for vector search
        
    Returns:
        Search results with relevant document chunks
    """
    # Check cache first
    cache_key = get_cache_key(query, max_num_results, rewrite_query)
    cached_results = get_cached_results(cache_key)
    if cached_results:
        return cached_results
    
    # Cache miss - call OpenAI API
    logger.info(f"✗ Cache MISS: {cache_key} - calling OpenAI API")
    endpoint = f"https://api.openai.com/v1/vector_stores/{vector_store_id}/search"
    
    payload = {
        "query": query,
        "max_num_results": max_num_results,
        "rewrite_query": rewrite_query
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(endpoint, headers=openai_headers, json=payload)
        response.raise_for_status()
        results = response.json()
        
        # Cache the results
        set_cached_results(cache_key, results)
        
        return results


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "AI Knowledge Base API",
        "version": "1.0.0",
        "endpoints": {
            "search": "/api/search",
            "health": "/health",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    db_status = "connected"
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        db_pool.putconn(conn)
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    cache_status = "disabled"
    if redis_client:
        try:
            redis_client.ping()
            cache_status = "connected"
        except Exception as e:
            cache_status = f"error: {str(e)}"
    
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "vector_store_id": vector_store_id,
        "database": db_status,
        "cache": cache_status
    }


@app.get("/api/file/{sha256}")
async def download_file(sha256: str):
    """
    Proxy endpoint for downloading original files
    
    Args:
        sha256: File SHA256 hash
        
    Returns:
        Redirect to presigned S3 URL
    """
    logger.info(f"File download request for sha256: {sha256[:16]}...")
    url = generate_presigned_url(sha256, file_type="original")
    if not url:
        logger.error(f"File not found in database: {sha256[:16]}...")
        raise HTTPException(status_code=404, detail="File not found")
    logger.info(f"Redirecting to S3 URL for {sha256[:16]}...")
    return RedirectResponse(url=url)


@app.get("/api/text/{sha256}")
async def download_text(sha256: str):
    """
    Proxy endpoint for downloading processed text files
    
    Args:
        sha256: File SHA256 hash
        
    Returns:
        Redirect to presigned S3 URL
    """
    logger.info(f"Text download request for sha256: {sha256[:16]}...")
    url = generate_presigned_url(sha256, file_type="text")
    if not url:
        logger.error(f"Text file not found in database: {sha256[:16]}...")
        raise HTTPException(status_code=404, detail="Text file not found")
    logger.info(f"Redirecting to S3 URL for text {sha256[:16]}...")
    return RedirectResponse(url=url)


@app.post("/api/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Perform semantic search over the knowledge base
    
    Args:
        request: SearchRequest with query and parameters
        
    Returns:
        SearchResponse with enriched results
    """
    try:
        # Get base URL for file proxies
        base_url = os.getenv("API_BASE_URL", "https://api.z10n.dev/api")
        
        # Convert single query to list for uniform processing
        queries = [request.query] if isinstance(request.query, str) else request.query
        
        logger.info(f"Search request: {len(queries)} queries")
        
        all_results = []
        
        # Execute search for each query
        for query_text in queries:
            logger.info(f"Processing query: '{query_text[:100]}'")
            
            # Perform vector store search - always fetch maximum (50) results
            raw_results = await vector_store_search(
                query=query_text,
                max_num_results=50,
                rewrite_query=request.rewrite_query
            )
            
            # Enrich results with metadata
            for item in raw_results.get('data', []):
                # Extract SHA256 from filename
                filename = item.get('filename', '')
                sha256_hash = filename.replace('.txt', '') if filename.endswith('.txt') else None
                
                if not sha256_hash:
                    continue
                
                # Get metadata from database with short proxy URLs
                metadata = get_file_metadata(sha256_hash, base_url)
                
                # Build content list for this chunk
                content = []
                for content_item in item.get('content', []):
                    if content_item.get('type') == 'text':
                        content.append(ContentItem(
                            type='text',
                            text=content_item.get('text', '')
                        ))
                
                # Add each chunk as a separate result
                all_results.append(SearchResult(
                    score=item.get('score', 0.0),
                    content=content,
                    metadata=metadata
                ))
        
        # Sort all results by score (highest first)
        all_results.sort(key=lambda x: x.score, reverse=True)
        
        # Build query string for response
        query_string = " | ".join(queries) if len(queries) > 1 else queries[0]
        
        logger.info(f"Search completed: {len(all_results)} results found from {len(queries)} queries")
        
        return SearchResponse(
            query=query_string,
            results=all_results,
            count=len(all_results)
        )
        
    except httpx.HTTPStatusError as e:
        logger.error(f"OpenAI API error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"OpenAI API error: {e.response.text}"
        )
    except Exception as e:
        logger.error(f"Search error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/search", response_model=SearchResponse)
async def search_get(
    qhu: str = Query(..., description="Hungarian search query (required)"),
    qen: str = Query(..., description="English search query (required)"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)")
):
    """
    GET endpoint for bilingual search with automatic pagination based on 100k character limit
    
    Args:
        qhu: Hungarian search query (required)
        qen: English search query (required)
        page: Page number (1-indexed)
        
    Returns:
        SearchResponse with paginated results (max 100,000 characters per page)
        
    Examples:
        /api/search?qhu=Holokauszt oktatás&qen=Holocaust education&page=1
    """
    # Both queries required
    request = SearchRequest(
        query=[qhu, qen],
        rewrite_query=True
    )
    
    # Get full results
    full_response = await search(request)
    
    # Apply pagination based on 100k character limit
    max_chars = 70000  # Safety margin for JSON formatting
    total_results = len(full_response.results)
    
    # Build pages dynamically by measuring actual response size
    pages = []
    current_page = []
    
    for result in full_response.results:
        # Try adding this result
        test_page = current_page + [result]
        
        # Build test response to measure actual size
        test_response = SearchResponse(
            query=full_response.query,
            results=test_page,
            count=len(test_page),
            total=total_results,
            page=1,
            page_size=len(test_page),
            has_more=True
        )
        
        response_size = len(test_response.model_dump_json())
        
        # If adding this result exceeds limit and we have results, start new page
        if response_size > max_chars and current_page:
            pages.append(current_page)
            current_page = [result]
        else:
            current_page = test_page
    
    # Add last page if not empty
    if current_page:
        pages.append(current_page)
    
    # Get requested page (default to empty if page doesn't exist)
    if page > len(pages):
        paginated_results = []
        page_size = 0
    else:
        paginated_results = pages[page - 1]
        page_size = len(paginated_results)
    
    has_more = page < len(pages)
    
    logger.info(f"Pagination: {len(pages)} pages total, page {page} has {page_size} results")
    
    return SearchResponse(
        query=full_response.query,
        results=paginated_results,
        count=len(paginated_results),
        total=total_results,
        page=page,
        page_size=page_size,
        has_more=has_more
    )


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
