#!/usr/bin/env python3
"""
AI Knowledge Base API Service
FastAPI service for semantic search over the vector store
"""

import os
import sys
import logging
from typing import Dict, List, Optional, Any, Union, Set
from contextlib import asynccontextmanager, contextmanager
from functools import lru_cache

import psycopg2
from psycopg2 import pool
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import httpx
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

class Config:
    """Application configuration"""
    # OpenAI
    OPENAI_API_KEY: str = os.getenv('OPENAI_API_KEY', '')
    VECTOR_STORE_ID: str = os.getenv('VECTOR_STORE_ID', '')
    OPENAI_TIMEOUT: int = 30
    OPENAI_MAX_RETRIES: int = 3
    
    # Database
    DB_HOST: str = os.getenv("POSTGRES_HOST", "postgres")
    DB_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    DB_NAME: str = os.getenv("POSTGRES_DB", "ai_knowledge_base")
    DB_USER: str = os.getenv("POSTGRES_USER", "postgres")
    DB_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    DB_MIN_CONN: int = 2
    DB_MAX_CONN: int = 10
    
    # S3
    S3_ENDPOINT: str = os.getenv("S3_ENDPOINT", "")
    S3_REGION: str = os.getenv("S3_REGION", "us-east-1")
    S3_BUCKET: str = os.getenv("S3_BUCKET", "")
    S3_ACCESS_KEY: str = os.getenv("S3_ACCESS_KEY", "")
    S3_SECRET_KEY: str = os.getenv("S3_SECRET_KEY", "")
    S3_PRESIGNED_URL_EXPIRY: int = 604800  # 7 days
    
    # API
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    CORS_ORIGINS: List[str] = os.getenv("CORS_ORIGINS", "*").split(",")
    MAX_RESULTS_LIMIT: int = 50
    DEFAULT_MAX_RESULTS: int = 10
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        if not cls.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required")
        if not cls.VECTOR_STORE_ID:
            raise ValueError("VECTOR_STORE_ID is required")
        if not cls.S3_BUCKET:
            raise ValueError("S3_BUCKET is required")


config = Config()


# ============================================================================
# Models
# ============================================================================

class ContentItem(BaseModel):
    """Content chunk item"""
    type: str
    text: str


class FileMetadata(BaseModel):
    """File metadata from database"""
    original_name: str
    sha256: str
    original_file_url: Optional[str] = None
    processed_text_url: Optional[str] = None


class SearchResult(BaseModel):
    """Single search result with score, content, and metadata"""
    score: float = Field(..., ge=0.0, le=1.0)
    content: List[ContentItem]
    metadata: Optional[FileMetadata] = None


class SearchRequest(BaseModel):
    """Search request parameters"""
    query: Union[str, List[str]] = Field(
        ..., 
        description="Single query string or list of queries for multi-language search"
    )
    max_results: int = Field(
        default=config.DEFAULT_MAX_RESULTS,
        ge=1,
        le=config.MAX_RESULTS_LIMIT,
        description=f"Maximum results per query (1-{config.MAX_RESULTS_LIMIT})"
    )
    rewrite_query: bool = Field(
        default=True,
        description="Let OpenAI optimize the query for better vector search"
    )
    merge_results: bool = Field(
        default=True,
        description="Deduplicate and merge chunks from same document across queries"
    )
    
    @validator('query')
    def validate_query(cls, v):
        """Validate query is not empty"""
        if isinstance(v, str):
            if not v.strip():
                raise ValueError("Query cannot be empty")
        elif isinstance(v, list):
            if not v or all(not q.strip() for q in v):
                raise ValueError("At least one non-empty query required")
        return v


class SearchResponse(BaseModel):
    """Search response with results"""
    query: str
    results: List[SearchResult]
    count: int
    
    class Config:
        schema_extra = {
            "example": {
                "query": "Holocaust education | Holokauszt oktatás",
                "results": [
                    {
                        "score": 0.89,
                        "content": [{"type": "text", "text": "Holocaust education content..."}],
                        "metadata": {
                            "original_name": "holocaust_guide.pdf",
                            "sha256": "abc123...",
                            "original_file_url": "https://...",
                            "processed_text_url": "https://..."
                        }
                    }
                ],
                "count": 1
            }
        }


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    vector_store_id: str
    database: str


# ============================================================================
# Service Layer
# ============================================================================

class DatabaseService:
    """Database operations service"""
    
    def __init__(self):
        self.pool: Optional[psycopg2.pool.SimpleConnectionPool] = None
        self._metadata_cache: Dict[str, Optional[FileMetadata]] = {}
    
    def initialize(self):
        """Initialize database connection pool"""
        try:
            self.pool = psycopg2.pool.SimpleConnectionPool(
                minconn=config.DB_MIN_CONN,
                maxconn=config.DB_MAX_CONN,
                host=config.DB_HOST,
                port=config.DB_PORT,
                database=config.DB_NAME,
                user=config.DB_USER,
                password=config.DB_PASSWORD
            )
            logger.info("Database connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
        finally:
            if conn:
                self.pool.putconn(conn)
    
    def get_file_metadata(self, sha256_hash: str, s3_service: 'S3Service') -> Optional[FileMetadata]:
        """
        Get file metadata by SHA256 hash with caching
        
        Args:
            sha256_hash: File SHA256 hash
            s3_service: S3 service for generating presigned URLs
            
        Returns:
            FileMetadata or None if not found
        """
        # Check cache
        if sha256_hash in self._metadata_cache:
            return self._metadata_cache[sha256_hash]
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
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
                    
                    if not result:
                        self._metadata_cache[sha256_hash] = None
                        return None
                    
                    original_name, s3_key, sha256 = result
                    
                    # Generate presigned URLs
                    original_file_url = None
                    processed_text_url = None
                    
                    if s3_key:
                        original_file_url = s3_service.generate_presigned_url(s3_key)
                        
                        # Text files: derivatives/{shard1}/{shard2}/{sha256}/text.txt
                        text_key = f"derivatives/{sha256[:2]}/{sha256[2:4]}/{sha256}/text.txt"
                        processed_text_url = s3_service.generate_presigned_url(text_key)
                    
                    metadata = FileMetadata(
                        original_name=original_name,
                        sha256=sha256,
                        original_file_url=original_file_url,
                        processed_text_url=processed_text_url
                    )
                    
                    # Cache result
                    self._metadata_cache[sha256_hash] = metadata
                    return metadata
        
        except Exception as e:
            logger.error(f"Database error fetching metadata for {sha256_hash}: {e}")
            return None
    
    def health_check(self) -> bool:
        """Check database health"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def close(self):
        """Close all database connections"""
        if self.pool:
            self.pool.closeall()
            logger.info("Database connection pool closed")


class S3Service:
    """S3 operations service"""
    
    def __init__(self):
        self.client = None
    
    def initialize(self):
        """Initialize S3 client"""
        try:
            s3_config = Config(
                signature_version='s3v4',
                retries={'max_attempts': 3, 'mode': 'adaptive'}
            )
            
            self.client = boto3.client(
                's3',
                region_name=config.S3_REGION,
                endpoint_url=config.S3_ENDPOINT,
                aws_access_key_id=config.S3_ACCESS_KEY,
                aws_secret_access_key=config.S3_SECRET_KEY,
                config=s3_config
            )
            logger.info("S3 client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            raise
    
    def generate_presigned_url(self, key: str) -> Optional[str]:
        """
        Generate presigned URL for S3 object
        
        Args:
            key: S3 object key
            
        Returns:
            Presigned URL or None if error
        """
        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': config.S3_BUCKET,
                    'Key': key
                },
                ExpiresIn=config.S3_PRESIGNED_URL_EXPIRY
            )
            return url
        except ClientError as e:
            logger.warning(f"Failed to generate presigned URL for {key}: {e}")
            return None


class VectorSearchService:
    """OpenAI Vector Store search service"""
    
    def __init__(self):
        self.headers = {
            'Authorization': f'Bearer {config.OPENAI_API_KEY}',
            'Content-Type': 'application/json'
        }
        self.endpoint = f"https://api.openai.com/v1/vector_stores/{config.VECTOR_STORE_ID}/search"
    
    async def search(
        self,
        query: str,
        max_results: int,
        rewrite_query: bool = True
    ) -> Dict[str, Any]:
        """
        Execute vector store search
        
        Args:
            query: Search query
            max_results: Maximum results to return
            rewrite_query: Whether to let OpenAI optimize the query
            
        Returns:
            Raw search results from OpenAI API
        """
        payload = {
            "query": query,
            "max_num_results": max_results,
            "rewrite_query": rewrite_query
        }
        
        async with httpx.AsyncClient(
            timeout=config.OPENAI_TIMEOUT,
            transport=httpx.AsyncHTTPTransport(retries=config.OPENAI_MAX_RETRIES)
        ) as client:
            response = await client.post(
                self.endpoint,
                headers=self.headers,
                json=payload
            )
            response.raise_for_status()
            return response.json()


class SearchService:
    """High-level search orchestration service"""
    
    def __init__(
        self,
        vector_service: VectorSearchService,
        db_service: DatabaseService,
        s3_service: S3Service
    ):
        self.vector_service = vector_service
        self.db_service = db_service
        self.s3_service = s3_service
    
    async def search(self, request: SearchRequest) -> SearchResponse:
        """
        Execute multi-query search with deduplication and enrichment
        
        Args:
            request: Search request parameters
            
        Returns:
            Search response with enriched results
        """
        # Normalize queries to list
        queries = [request.query] if isinstance(request.query, str) else request.query
        queries = [q.strip() for q in queries if q.strip()]
        
        if not queries:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one non-empty query required"
            )
        
        logger.info(
            f"Search: {len(queries)} queries, "
            f"max_results={request.max_results}, "
            f"merge={request.merge_results}"
        )
        
        # Track documents for deduplication
        seen_documents: Dict[str, Dict[str, Any]] = {}
        all_results: List[SearchResult] = []
        
        # Execute each query
        for query_text in queries:
            logger.info(f"Executing query: '{query_text[:80]}'")
            
            # Search vector store
            raw_results = await self.vector_service.search(
                query=query_text,
                max_results=request.max_results,
                rewrite_query=request.rewrite_query
            )
            
            # Process results
            for item in raw_results.get('data', []):
                result = self._process_search_item(item)
                if not result:
                    continue
                
                sha256_hash, search_result = result
                
                if request.merge_results:
                    self._merge_result(sha256_hash, search_result, seen_documents)
                else:
                    all_results.append(search_result)
        
        # Build final results
        if request.merge_results:
            all_results = self._build_merged_results(seen_documents)
        
        # Sort by score (highest first)
        all_results.sort(key=lambda x: x.score, reverse=True)
        
        # Apply limit only for single query or non-merged results
        if not request.merge_results or len(queries) == 1:
            all_results = all_results[:request.max_results]
        
        query_string = " | ".join(queries)
        
        logger.info(f"Search completed: {len(all_results)} results")
        
        return SearchResponse(
            query=query_string,
            results=all_results,
            count=len(all_results)
        )
    
    def _process_search_item(self, item: Dict[str, Any]) -> Optional[tuple[str, SearchResult]]:
        """
        Process a single search result item
        
        Returns:
            Tuple of (sha256_hash, SearchResult) or None if invalid
        """
        # Extract SHA256 from filename
        filename = item.get('filename', '')
        if not filename.endswith('.txt'):
            return None
        
        sha256_hash = filename.replace('.txt', '')
        if not sha256_hash:
            return None
        
        # Get metadata
        metadata = self.db_service.get_file_metadata(sha256_hash, self.s3_service)
        
        # Build content
        content = []
        for content_item in item.get('content', []):
            if content_item.get('type') == 'text':
                content.append(ContentItem(
                    type='text',
                    text=content_item.get('text', '')
                ))
        
        if not content:
            return None
        
        score = item.get('score', 0.0)
        
        search_result = SearchResult(
            score=score,
            content=content,
            metadata=metadata
        )
        
        return sha256_hash, search_result
    
    def _merge_result(
        self,
        sha256_hash: str,
        result: SearchResult,
        seen_documents: Dict[str, Dict[str, Any]]
    ):
        """
        Merge result into seen_documents, combining chunks and keeping highest score
        """
        if sha256_hash in seen_documents:
            doc_data = seen_documents[sha256_hash]
            
            # Merge unique content chunks
            existing_texts: Set[str] = doc_data['existing_texts']
            for chunk in result.content:
                if chunk.text not in existing_texts:
                    doc_data['content'].append(chunk)
                    existing_texts.add(chunk.text)
            
            # Keep highest score
            if result.score > doc_data['score']:
                doc_data['score'] = result.score
        else:
            # First occurrence of this document
            seen_documents[sha256_hash] = {
                'score': result.score,
                'content': result.content.copy(),
                'metadata': result.metadata,
                'existing_texts': {c.text for c in result.content}
            }
    
    def _build_merged_results(self, seen_documents: Dict[str, Dict[str, Any]]) -> List[SearchResult]:
        """Build SearchResult list from merged documents"""
        results = []
        for doc_data in seen_documents.values():
            results.append(SearchResult(
                score=doc_data['score'],
                content=doc_data['content'],
                metadata=doc_data['metadata']
            ))
        return results


# ============================================================================
# Application Setup
# ============================================================================

# Service instances
db_service = DatabaseService()
s3_service = S3Service()
vector_service = VectorSearchService()
search_service = SearchService(vector_service, db_service, s3_service)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown"""
    # Startup
    config.validate()
    db_service.initialize()
    s3_service.initialize()
    logger.info("API service initialized successfully")
    
    yield
    
    # Shutdown
    db_service.close()
    logger.info("API service shutdown complete")


# Initialize FastAPI app
app = FastAPI(
    title="AI Knowledge Base API",
    description="Semantic search API using OpenAI Vector Store",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", tags=["Info"])
async def root():
    """API information"""
    return {
        "service": "AI Knowledge Base API",
        "version": "2.0.0",
        "endpoints": {
            "search_post": "POST /api/search",
            "search_get": "GET /api/search",
            "health": "/health",
            "docs": "/docs"
        }
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint"""
    db_healthy = db_service.health_check()
    
    return HealthResponse(
        status="healthy" if db_healthy else "degraded",
        vector_store_id=config.VECTOR_STORE_ID,
        database="connected" if db_healthy else "disconnected"
    )


@app.post("/api/search", response_model=SearchResponse, tags=["Search"])
async def search_post(request: SearchRequest):
    """
    Semantic search (POST)
    
    Supports single or multiple queries for cross-language search.
    Results are deduplicated and chunks merged when merge_results=True.
    """
    try:
        return await search_service.search(request)
    except httpx.HTTPStatusError as e:
        logger.error(f"OpenAI API error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Vector search failed: {e.response.text}"
        )
    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal search error"
        )


@app.get("/api/search", response_model=SearchResponse, tags=["Search"])
async def search_get(
    qhu: Optional[str] = Query(None, description="Hungarian query"),
    qen: Optional[str] = Query(None, description="English query"),
    qen2: Optional[str] = Query(None, description="English query 2"),
    qen3: Optional[str] = Query(None, description="English query 3"),
    max_results: int = Query(
        config.DEFAULT_MAX_RESULTS,
        ge=1,
        le=config.MAX_RESULTS_LIMIT,
        description="Maximum results per query"
    ),
    rewrite: bool = Query(True, description="Optimize query for vector search"),
    merge: bool = Query(True, description="Merge and deduplicate results")
):
    """
    Semantic search (GET)
    
    Convenience endpoint for GET requests. Use query parameters for multiple languages.
    
    Examples:
    - /api/search?qen=Holocaust education&max_results=5
    - /api/search?qhu=vezetés&qen=leadership&max_results=15
    """
    # Collect queries
    queries = [q for q in [qhu, qen, qen2, qen3] if q]
    
    if not queries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one query parameter required (qhu, qen, qen2, qen3)"
        )
    
    request = SearchRequest(
        query=queries if len(queries) > 1 else queries[0],
        max_results=max_results,
        rewrite_query=rewrite,
        merge_results=merge
    )
    
    return await search_post(request)


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=config.API_PORT,
        log_level="info"
    )
