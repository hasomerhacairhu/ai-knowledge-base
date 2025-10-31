#!/usr/bin/env python3
"""
AI Knowledge Base API Service
FastAPI service for semantic search over the vector store
"""

import os
import sys
import logging
import psycopg2
from psycopg2 import pool
import boto3
from typing import Dict, List, Optional, Any, Union
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
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
    query: Union[str, List[str]] = Field(..., description="Search query or list of queries to merge results")
    max_results: int = Field(10, ge=1, le=50, description="Maximum number of results to return per query")
    rewrite_query: bool = Field(True, description="Whether to rewrite the query for better search results")
    multilingual: bool = Field(True, description="Enable multilingual search (searches in both Hungarian and English)")
    merge_results: bool = Field(True, description="Merge and deduplicate results from multiple queries")


class ContentItem(BaseModel):
    type: str
    text: str


class FileMetadata(BaseModel):
    original_name: str
    original_file_download_url: str
    processed_text_download_url: Optional[str] = None
    sha256: str


class SearchResult(BaseModel):
    score: float
    content: List[ContentItem]
    metadata: Optional[FileMetadata] = None


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    count: int


# Global clients
s3_client = None
openai_headers = None
vector_store_id = None
db_pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize clients on startup"""
    global s3_client, openai_headers, vector_store_id, db_pool
    
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
    
    logger.info("✅ API service initialized")
    yield
    
    # Cleanup
    if db_pool:
        db_pool.closeall()
        logger.info("🛑 PostgreSQL connection pool closed")
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


def get_file_metadata(sha256_hash: str) -> Optional[FileMetadata]:
    """
    Look up file metadata from PostgreSQL database by SHA256 hash.
    
    Args:
        sha256_hash: SHA256 hash extracted from OpenAI filename
        
    Returns:
        FileMetadata object or None
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
            
            # Generate S3 presigned URLs (7 days)
            original_file_download_url = None
            processed_text_download_url = None
            
            if s3_key:
                try:
                    # Original file download URL (7 days = 604800 seconds)
                    original_file_download_url = s3_client.generate_presigned_url(
                        'get_object',
                        Params={
                            'Bucket': os.getenv("S3_BUCKET"),
                            'Key': s3_key
                        },
                        ExpiresIn=604800
                    )
                    
                    # Processed text file download URL (7 days)
                    # Text files are stored as: derivatives/{shard1}/{shard2}/{sha256}/text.txt
                    shard1 = sha256[:2]
                    shard2 = sha256[2:4]
                    txt_key = f"derivatives/{shard1}/{shard2}/{sha256}/text.txt"
                    processed_text_download_url = s3_client.generate_presigned_url(
                        'get_object',
                        Params={
                            'Bucket': os.getenv("S3_BUCKET"),
                            'Key': txt_key
                        },
                        ExpiresIn=604800
                    )
                        
                except Exception as e:
                    logger.error(f"⚠️  Could not generate S3 URL for {sha256_hash}: {e}")
            
            return FileMetadata(
                original_name=original_name,
                original_file_download_url=original_file_download_url or "",
                processed_text_download_url=processed_text_download_url,
                sha256=sha256
            )
        
        return None
        
    except Exception as e:
        logger.error(f"⚠️  Database error for sha256 {sha256_hash}: {e}")
        return None
    finally:
        if conn:
            db_pool.putconn(conn)


async def vector_store_search(
    query: str,
    max_num_results: int = 10,
    rewrite_query: bool = True
) -> Dict[str, Any]:
    """
    Direct search of vector store without LLM generation.
    
    Args:
        query: Search query
        max_num_results: Number of results to return (1-50)
        rewrite_query: Whether to optimize query for vector search
        
    Returns:
        Search results with relevant document chunks
    """
    endpoint = f"https://api.openai.com/v1/vector_stores/{vector_store_id}/search"
    
    payload = {
        "query": query,
        "max_num_results": max_num_results,
        "rewrite_query": rewrite_query
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(endpoint, headers=openai_headers, json=payload)
        response.raise_for_status()
        return response.json()


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
    
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "vector_store_id": vector_store_id,
        "database": db_status
    }


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
        # Convert single query to list for uniform processing
        queries = [request.query] if isinstance(request.query, str) else request.query
        
        logger.info(f"Search request: {len(queries)} queries, max_results={request.max_results}, multilingual={request.multilingual}")
        
        all_results = []
        seen_sha256 = set()  # Track seen documents for deduplication
        
        # Execute search for each query
        for query_text in queries:
            logger.info(f"Processing query: '{query_text[:100]}'")
            
            # Build search query (with multilingual support if enabled)
            search_query = query_text
            if request.multilingual:
                # Enhance query to work across Hungarian and English
                search_query = f"{query_text}"
                logger.info(f"Multilingual search enabled for query: '{search_query[:100]}'")
            
            # Perform vector store search
            raw_results = await vector_store_search(
                query=search_query,
                max_num_results=request.max_results * 2 if request.multilingual else request.max_results,
                rewrite_query=request.rewrite_query
            )
            
            # Enrich results with metadata
            for item in raw_results.get('data', []):
                # Extract SHA256 from filename
                filename = item.get('filename', '')
                sha256_hash = filename.replace('.txt', '') if filename.endswith('.txt') else None
                
                # Skip if already seen (deduplication)
                if request.merge_results and sha256_hash and sha256_hash in seen_sha256:
                    continue
                
                if sha256_hash:
                    seen_sha256.add(sha256_hash)
                
                # Get metadata from database
                metadata = None
                if sha256_hash:
                    metadata = get_file_metadata(sha256_hash)
                
                # Build content list
                content = []
                for content_item in item.get('content', []):
                    if content_item.get('type') == 'text':
                        content.append(ContentItem(
                            type='text',
                            text=content_item.get('text', '')
                        ))
                
                all_results.append(SearchResult(
                    score=item.get('score', 0.0),
                    content=content,
                    metadata=metadata
                ))
        
        # Sort all results by score (highest first)
        all_results.sort(key=lambda x: x.score, reverse=True)
        
        # Limit to requested count
        if len(all_results) > request.max_results:
            all_results = all_results[:request.max_results]
        
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
    qhu: Optional[str] = Query(None, description="Hungarian search query"),
    qen: Optional[str] = Query(None, description="English search query"),
    max_results: int = Query(10, ge=1, le=50, description="Maximum results"),
    rewrite: bool = Query(True, description="Rewrite query for search"),
    multilingual: bool = Query(True, description="Enable multilingual search"),
    merge_results: bool = Query(True, description="Merge and deduplicate results")
):
    """
    GET endpoint for search (convenience method)
    
    Args:
        qhu: Hungarian search query (optional)
        qen: English search query (optional)
        qen2, qen3: Additional English search queries (optional)
        max_results: Maximum number of results
        rewrite: Whether to rewrite the query
        multilingual: Enable multilingual search (searches in both languages)
        merge_results: Merge and deduplicate results from multiple queries
        
    Returns:
        SearchResponse with enriched results
        
    Examples:
        /api/search?qen=Holocaust education&max_results=5
        /api/search?qen=Holocaust education&qhu=Holokauszt oktatás&max_results=10
        /api/search?qhu=vezetés&qen=leadership&qen2=organizational culture&max_results=15
    """
    # Collect all non-None queries
    queries = []
    if qhu:
        queries.append(qhu)
    if qen:
        queries.append(qen)
    if qen2:
        queries.append(qen2)
    if qen3:
        queries.append(qen3)
    
    # Must have at least one query
    if not queries:
        raise HTTPException(status_code=400, detail="At least one query parameter (qhu, qen) is required")
    
    request = SearchRequest(
        query=queries if len(queries) > 1 else queries[0],
        max_results=max_results,
        multilingual=multilingual,
        merge_results=merge_results,
        rewrite_query=rewrite
    )
    return await search(request)


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
