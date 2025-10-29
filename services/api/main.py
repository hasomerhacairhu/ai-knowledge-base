#!/usr/bin/env python3
"""
AI Knowledge Base API Service
FastAPI service for semantic search over the vector store
"""

import os
import sqlite3
import boto3
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()


# Request/Response Models
class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    max_results: int = Field(10, ge=1, le=50, description="Maximum number of results")
    rewrite_query: bool = Field(True, description="Whether to optimize query for vector search")


class ContentItem(BaseModel):
    type: str
    text: str


class FileMetadata(BaseModel):
    original_name: Optional[str] = None
    drive_path: Optional[str] = None
    mime_type: Optional[str] = None
    drive_file_id: Optional[str] = None
    drive_url: Optional[str] = None
    s3_key: Optional[str] = None
    s3_presigned_url: Optional[str] = None
    sha256: Optional[str] = None


class SearchResult(BaseModel):
    filename: str
    file_id: str
    score: float
    content: List[ContentItem]
    attributes: Optional[Dict] = None
    metadata: Optional[FileMetadata] = None


class SearchResponse(BaseModel):
    query: str
    search_query: str
    results: List[SearchResult]
    count: int


# Global clients
s3_client = None
openai_headers = None
vector_store_id = None
database_path = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize clients on startup"""
    global s3_client, openai_headers, vector_store_id, database_path
    
    # Initialize S3 client
    config = Config(
        region_name=os.getenv("S3_REGION", "us-east-1"),
        retries={'max_attempts': 3, 'mode': 'adaptive'}
    )
    
    s3_client = boto3.client(
        's3',
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
    
    # Database path
    database_path = os.getenv("DATABASE_PATH", "/app/data/pipeline.db")
    
    print("✅ API service initialized")
    yield
    print("🛑 API service shutting down")


# Initialize FastAPI app
app = FastAPI(
    title="AI Knowledge Base API",
    description="Semantic search API for AI Knowledge Base using OpenAI Vector Store",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_file_metadata(sha256_hash: str) -> Optional[FileMetadata]:
    """
    Look up file metadata from database by SHA256 hash.
    
    Args:
        sha256_hash: SHA256 hash extracted from OpenAI filename
        
    Returns:
        FileMetadata object or None
    """
    try:
        conn = sqlite3.connect(database_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                dfm.original_name,
                dfm.drive_path,
                dfm.drive_mime_type,
                dfm.drive_file_id,
                fs.s3_key,
                fs.sha256
            FROM drive_file_mapping dfm
            JOIN file_state fs ON dfm.sha256 = fs.sha256
            WHERE fs.sha256 = ?
            LIMIT 1
        ''', (sha256_hash,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            original_name, drive_path, mime_type, drive_file_id, s3_key, sha256 = result
            
            # Generate Drive URL
            drive_url = f"https://drive.google.com/file/d/{drive_file_id}/view" if drive_file_id else None
            
            # Generate S3 presigned URL
            s3_presigned_url = None
            if s3_key:
                try:
                    s3_presigned_url = s3_client.generate_presigned_url(
                        'get_object',
                        Params={
                            'Bucket': os.getenv("S3_BUCKET"),
                            'Key': s3_key
                        },
                        ExpiresIn=3600  # URL valid for 1 hour
                    )
                except Exception as e:
                    print(f"⚠️  Could not generate S3 URL: {e}")
            
            return FileMetadata(
                original_name=original_name,
                drive_path=drive_path,
                mime_type=mime_type,
                drive_file_id=drive_file_id,
                drive_url=drive_url,
                s3_key=s3_key,
                s3_presigned_url=s3_presigned_url,
                sha256=sha256
            )
        
        return None
        
    except Exception as e:
        print(f"⚠️  Database error: {e}")
        return None


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
    return {
        "status": "healthy",
        "vector_store_id": vector_store_id,
        "database": os.path.exists(database_path)
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
        # Perform vector store search
        raw_results = await vector_store_search(
            query=request.query,
            max_num_results=request.max_results,
            rewrite_query=request.rewrite_query
        )
        
        # Enrich results with metadata
        enriched_results = []
        for item in raw_results.get('data', []):
            # Extract SHA256 from filename
            filename = item.get('filename', '')
            sha256_hash = filename.replace('.txt', '') if filename.endswith('.txt') else None
            
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
            
            enriched_results.append(SearchResult(
                filename=filename,
                file_id=item.get('file_id', ''),
                score=item.get('score', 0.0),
                content=content,
                attributes=item.get('attributes'),
                metadata=metadata
            ))
        
        return SearchResponse(
            query=request.query,
            search_query=raw_results.get('search_query', request.query),
            results=enriched_results,
            count=len(enriched_results)
        )
        
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"OpenAI API error: {e.response.text}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/search", response_model=SearchResponse)
async def search_get(
    q: str = Query(..., description="Search query"),
    max_results: int = Query(10, ge=1, le=50, description="Maximum results"),
    rewrite: bool = Query(True, description="Rewrite query for search")
):
    """
    GET endpoint for search (convenience method)
    
    Args:
        q: Search query
        max_results: Maximum number of results
        rewrite: Whether to rewrite the query
        
    Returns:
        SearchResponse with enriched results
    """
    request = SearchRequest(
        query=q,
        max_results=max_results,
        rewrite_query=rewrite
    )
    return await search(request)


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
