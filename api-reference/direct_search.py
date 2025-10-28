#!/usr/bin/env python3
"""
Direct Vector Store Search - NO LLM Required!

This script uses OpenAI's undocumented Vector Store Search API endpoint
to perform semantic search WITHOUT using an LLM model. This provides:

1. Instant results (no LLM generation overhead)
2. Fixed cost ($2.50 per 1,000 searches)
3. Raw document chunks with relevance scores
4. Perfect for building custom solutions on top
5. Full metadata enrichment:
   - Original filenames from Google Drive
   - Google Drive URLs (clickable links)
   - S3 presigned URLs (valid for 1 hour)
   - File paths and MIME types
   - Document chunks with relevance scores

Technical Details:
- Endpoint: POST https://api.openai.com/v1/vector_stores/{id}/search
- Returns: Document chunks with relevance scores (0.0-1.0)
- No token costs - just semantic search
- Response includes: filename, file_id, content, attributes
- Enriched with: Drive URLs, S3 signed URLs, original filenames from database

Database Integration:
- Queries pipeline.db to match SHA256 hashes
- Joins file_state and drive_file_mapping tables
- Generates presigned S3 URLs on-the-fly
- Provides complete file provenance

Usage:
  uv run python direct_search.py "Your query"
  uv run python direct_search.py "Your query" --max-results 20
  
Examples:
  uv run python direct_search.py "What is Centropa?"
  uv run python direct_search.py "Ki volt Koltai?" --max-results 5
"""

import os
import sys
import httpx
import sqlite3
import boto3
from botocore.config import Config
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

load_dotenv()


def get_s3_client():
    """Initialize S3 client for generating presigned URLs"""
    config = Config(
        region_name=os.getenv("S3_REGION", "us-east-1"),
        retries={'max_attempts': 3, 'mode': 'adaptive'}
    )
    
    return boto3.client(
        's3',
        endpoint_url=os.getenv("S3_ENDPOINT"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
        config=config
    )


def get_file_metadata(sha256_hash: str) -> Optional[Dict]:
    """
    Look up file metadata from database by SHA256 hash.
    Returns Drive URL, S3 key, original filename, etc.
    
    Args:
        sha256_hash: SHA256 hash extracted from OpenAI filename
        
    Returns:
        Dictionary with metadata or None
    """
    try:
        conn = sqlite3.connect('./data/pipeline.db')
        cursor = conn.cursor()
        
        # Query both file_state and drive_file_mapping
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
                    s3_client = get_s3_client()
                    s3_presigned_url = s3_client.generate_presigned_url(
                        'get_object',
                        Params={
                            'Bucket': os.getenv("S3_BUCKET"),
                            'Key': s3_key
                        },
                        ExpiresIn=3600  # URL valid for 1 hour
                    )
                except Exception as e:
                    print(f"⚠️  Could not generate S3 URL: {e}", file=sys.stderr)
            
            return {
                'original_name': original_name,
                'drive_path': drive_path,
                'mime_type': mime_type,
                'drive_file_id': drive_file_id,
                'drive_url': drive_url,
                's3_key': s3_key,
                's3_presigned_url': s3_presigned_url,
                'sha256': sha256
            }
        
        return None
        
    except Exception as e:
        print(f"⚠️  Database error: {e}", file=sys.stderr)
        return None

def get_headers() -> dict:
    """Get HTTP headers with API key."""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set in .env file")
    return {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

def vector_store_search(
    vector_store_id: str,
    query: str,
    max_num_results: int = 10,
    rewrite_query: bool = True
) -> Dict[str, Any]:
    """
    Direct search of vector store without LLM generation.
    
    Args:
        vector_store_id: ID of the vector store
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
    
    response = httpx.post(endpoint, headers=get_headers(), json=payload, timeout=30.0)
    response.raise_for_status()
    return response.json()

def display_results(results: Dict[str, Any], query: str, preview_length: int = 500, show_full: bool = False):
    """
    Display search results with enriched metadata
    
    Args:
        results: Search results from vector store
        query: Original search query
        preview_length: Number of characters to show (default 500, 0 for full)
        show_full: If True, show complete content regardless of length
    """
    print("\n" + "="*100)
    print("🔍 DIRECT VECTOR SEARCH (NO LLM)")
    print("="*100)
    
    print(f"\n❓ Query: {query}")
    print(f"🎯 Search Query Used: {results.get('search_query', 'N/A')}")
    
    data = results.get('data', [])
    print(f"\n📚 Found {len(data)} relevant document chunks:")
    
    for idx, item in enumerate(data, 1):
        print("\n" + "-"*100)
        print(f"\n[{idx}] 📄 {item.get('filename', 'Unknown')}")
        print(f"    🎯 Relevance Score: {item.get('score', 0):.4f}")
        print(f"    🆔 File ID: {item.get('file_id', 'N/A')}")
        
        # Extract SHA256 from filename (format: sha256.txt)
        filename = item.get('filename', '')
        sha256_hash = filename.replace('.txt', '') if filename.endswith('.txt') else None
        
        # Get enriched metadata from database
        if sha256_hash:
            metadata = get_file_metadata(sha256_hash)
            if metadata:
                print(f"\n    📝 Original Filename: {metadata['original_name']}")
                print(f"    📁 Drive Path: {metadata['drive_path']}")
                print(f"    📄 MIME Type: {metadata['mime_type']}")
                
                if metadata['drive_url']:
                    print(f"    🔗 Drive URL: {metadata['drive_url']}")
                
                if metadata['s3_presigned_url']:
                    print(f"    ☁️  S3 Signed URL (1h): {metadata['s3_presigned_url']}")
                else:
                    print(f"    ☁️  S3 Key: {metadata['s3_key']}")
        
        # Display content preview
        content_list = item.get('content', [])
        if content_list:
            # Combine text content
            text_content = ""
            for content_item in content_list:
                if content_item.get('type') == 'text':
                    text_content += content_item.get('text', '')
            
            if text_content:
                full_length = len(text_content)
                
                # Determine what to show
                if show_full or preview_length == 0:
                    preview = text_content
                    print(f"\n    📝 Full Content ({full_length} chars):")
                else:
                    preview = text_content[:preview_length]
                    if len(text_content) > preview_length:
                        preview += "..."
                    print(f"\n    📝 Content Preview ({preview_length}/{full_length} chars):")
                
                # Indent each line of preview
                for line in preview.split('\n'):
                    print(f"       {line}")
        
        # Display attributes if present
        attributes = item.get('attributes', {})
        if attributes:
            print(f"\n    🏷️  Attributes: {attributes}")

def direct_search(query: str, max_results: int = 10, preview_length: int = 500, show_full: bool = False):
    """
    Perform direct vector store search.
    
    Args:
        query: Search query
        max_results: Number of results to return
        preview_length: Characters to show in preview (0 for full)
        show_full: Show complete content
    """
    
    vector_store_id = os.getenv("VECTOR_STORE_ID")
    
    if not vector_store_id:
        print("Error: VECTOR_STORE_ID not set in .env file", file=sys.stderr)
        sys.exit(1)
    
    print("\n⏳ Searching vector store...")
    
    try:
        results = vector_store_search(
            vector_store_id=vector_store_id,
            query=query,
            max_num_results=max_results,
            rewrite_query=True
        )
        
        display_results(results, query, preview_length=preview_length, show_full=show_full)
        
        print(f"\n💰 Cost: ~$0.0025 per search (1/1000th of 1k searches)")
        print(f"⚡ Speed: Instant - no LLM generation overhead!")
        
    except httpx.HTTPStatusError as e:
        print(f"\n❌ HTTP Error: {e.response.status_code}", file=sys.stderr)
        print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Direct Vector Store Search - NO LLM, just semantic search!")
        print("\nUsage: uv run python direct_search.py 'Your question here' [options]")
        print("\nOptions:")
        print("  --max-results N        Number of results (default: 10)")
        print("  --preview-length N     Preview characters (default: 500, 0 for full)")
        print("  --full                 Show complete content (no truncation)")
        print("\nExamples:")
        print("  uv run python direct_search.py 'What is Centropa?'")
        print("  uv run python direct_search.py 'Ki volt Koltai István?' --full")
        print("  uv run python direct_search.py 'Holocaust education' --max-results 20 --preview-length 1000")
        print("  uv run python direct_search.py 'Kindertransport' --preview-length 0  # Show all content")
        print("\nBenefits:")
        print("  ⚡ Lightning fast - no LLM generation")
        print("  💰 Super cheap - $2.50/1k searches vs LLM token costs")
        print("  🎯 Pure semantic search with relevance scores")
        print("  📊 Get raw document chunks for your own processing")
        print("  🔗 Direct access to source files via Drive + S3 URLs")
        sys.exit(1)
    
    # Parse arguments
    max_results = 10
    preview_length = 500
    show_full = False
    query_parts = []
    
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '--max-results' and i + 1 < len(sys.argv):
            max_results = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == '--preview-length' and i + 1 < len(sys.argv):
            preview_length = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == '--full':
            show_full = True
            i += 1
        else:
            query_parts.append(sys.argv[i])
            i += 1
    
    if not query_parts:
        print("Error: No query provided", file=sys.stderr)
        sys.exit(1)
    
    query = " ".join(query_parts)
    direct_search(query, max_results, preview_length=preview_length, show_full=show_full)
