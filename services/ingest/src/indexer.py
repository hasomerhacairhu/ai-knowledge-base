"""OpenAI Vector Store indexer"""

import json
import time
from datetime import datetime
from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI, RateLimitError, APIError
from tqdm import tqdm

from .config import Config
from .database import Database, FileStatus
from .utils import S3Client, setup_logging, ProgressTracker

logger = setup_logging(__name__)


def retry_with_exponential_backoff(
    func,
    max_retries: int = 5,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0
):
    """
    Retry a function with exponential backoff for rate limits
    
    Args:
        func: Function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Multiplier for delay after each retry
    
    Returns:
        Result of func() if successful
    
    Raises:
        Last exception if all retries exhausted
    """
    delay = initial_delay
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return func()
        except RateLimitError as e:
            last_exception = e
            if attempt < max_retries - 1:
                # Calculate delay with exponential backoff
                wait_time = min(delay * (backoff_factor ** attempt), max_delay)
                logger.warning(f"   Rate limit hit, retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                logger.error(f"   Rate limit: Max retries ({max_retries}) exhausted")
                raise
        except APIError as e:
            last_exception = e
            # Retry on 5xx server errors, but not on 4xx client errors
            if 500 <= e.status_code < 600 and attempt < max_retries - 1:
                wait_time = min(delay * (backoff_factor ** attempt), max_delay)
                logger.warning(f"   API error {e.status_code}, retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
            else:
                raise
    
    raise last_exception


class VectorStoreIndexer:
    """Index processed text files into OpenAI Vector Store"""
    
    def __init__(self, config: Config, database: Database, dry_run: bool = False, max_workers: Optional[int] = None):
        self.config = config
        self.database = database
        self.dry_run = dry_run
        self.max_workers = max_workers or config.indexer_max_workers
        self.quiet_mode = False
        
        # Initialize S3 client with connection pooling
        self.s3 = S3Client(
            endpoint=config.s3_endpoint,
            access_key=config.s3_access_key,
            secret_key=config.s3_secret_key,
            bucket=config.s3_bucket,
            region=config.s3_region
        )
        
        # Initialize OpenAI client
        self.openai_client = OpenAI(api_key=config.openai_api_key)
    
    def list_unindexed_files(self, max_files: Optional[int] = None) -> List[Tuple[str, str, dict]]:
        """
        List processed text files that haven't been indexed yet
        
        Uses database queries instead of S3 listing for O(1) lookups.
        
        Returns:
            List of tuples: (text_key, sha256, file_record_dict)
        """
        logger.info(f"🔍 Querying database for files ready to index...")
        
        try:
            # Query database for files with status=PROCESSED
            files = self.database.get_files_for_indexing(limit=max_files)
            
            logger.info(f"✅ Found {len(files)} unindexed files")
            
            # Convert to expected format with text_key
            result = []
            for file in files:
                sha256 = file["sha256"]
                shard1 = sha256[:2]
                shard2 = sha256[2:4]
                text_key = f"derivatives/{shard1}/{shard2}/{sha256}/text.txt"
                result.append((text_key, sha256, file))
            
            return result
        
        except Exception as e:
            logger.error(f"Error querying database: {e}")
            return []
    
    def index_file(self, text_key: str, sha256: str, file_record: dict) -> Optional[str]:
        """
        Index a single text file to Vector Store with atomic database updates
        
        Uses database for state management instead of S3 markers.
        Implements retry logic with exponential backoff for rate limits.
        
        Args:
            text_key: S3 key for text file
            sha256: SHA-256 hash
            file_record: Database file record
        
        Returns:
            OpenAI file ID if successful, None otherwise
        """
        def log(msg: str):
            if not self.quiet_mode:
                logger.info(msg)
        
        log(f"📄 Indexing: {sha256}")
        log(f"   Original: {file_record.get('original_name', 'unknown')}")
        
        if self.dry_run:
            log(f"   [DRY RUN] Would upload to Vector Store: {self.config.vector_store_id}")
            return f"file-{sha256[:8]}-dryrun"
        
        try:
            # Mark as INDEXING in database (prevents race conditions, clear previous errors)
            log("   🔒 Marking as indexing in database...")
            self.database.upsert_file(
                sha256=sha256,
                s3_key=file_record["s3_key"],
                status=FileStatus.INDEXING,
                error_message="",  # Clear previous errors when retrying
                error_type=""
            )
            
            # Download text content - STREAM for memory efficiency
            log("   📥 Downloading text...")
            text_stream, _ = self.s3.get_object_stream(text_key)
            
            # Upload to OpenAI with retry logic
            log("   📤 Uploading to OpenAI...")
            
            # Wrap the streaming body as a file-like object with a name
            # The boto3 StreamingBody is already a file-like object
            text_stream.name = f"{sha256}.txt"
            
            # Upload file with exponential backoff
            def upload_file():
                return self.openai_client.files.create(
                    file=text_stream,
                    purpose='assistants'
                )
            
            file_response = retry_with_exponential_backoff(upload_file)
            file_id = file_response.id
            log(f"   ✅ Uploaded file: {file_id}")
            
            # Add to Vector Store with retry logic
            log(f"   📚 Adding to Vector Store: {self.config.vector_store_id}")
            
            def add_to_vector_store():
                return self.openai_client.vector_stores.files.create(
                    vector_store_id=self.config.vector_store_id,
                    file_id=file_id
                )
            
            retry_with_exponential_backoff(add_to_vector_store)
            log("   ✅ Added to Vector Store")
            
            # Mark as INDEXED in database (atomic operation, clear any previous errors)
            self.database.upsert_file(
                sha256=sha256,
                s3_key=file_record["s3_key"],
                status=FileStatus.INDEXED,
                openai_file_id=file_id,
                vector_store_id=self.config.vector_store_id,
                error_message="",  # Empty string to clear error
                error_type=""
            )
            
            return file_id
        
        except Exception as e:
            logger.error(f"   Error indexing file: {e}", exc_info=True)
            
            # Mark as FAILED_INDEX in database
            if not self.dry_run:
                self.database.upsert_file(
                    sha256=sha256,
                    s3_key=file_record["s3_key"],
                    status=FileStatus.FAILED_INDEX,
                    error_message=str(e),
                    error_type=type(e).__name__
                )
                logger.info(f"   🗑️  Marked as failed in database")
            
            return None
    
    def index_batch(self, max_files: Optional[int] = None, parallel: bool = True, filter_sha256: Optional[List[str]] = None) -> Tuple[int, int]:
        """
        Index a batch of processed text files
        
        Args:
            max_files: Maximum number of files to index
            parallel: Use parallel processing (default: True, use fewer workers for API limits)
            filter_sha256: Optional list of SHA256 hashes to index (for full pipeline)
        
        Returns:
            Tuple of (successful_count, failed_count)
        """
        logger.info("="*80)
        logger.info("📚 Starting Vector Store Indexing")
        if self.dry_run:
            logger.info("   [DRY RUN MODE - No changes will be made]")
        if parallel:
            logger.info(f"   [PARALLEL MODE - {self.max_workers} workers (limited for API rate limits)]")
        if filter_sha256:
            logger.info(f"   [FILTERED MODE - Indexing {len(filter_sha256)} specific files from process stage]")
        logger.info(f"   Vector Store ID: {self.config.vector_store_id}")
        logger.info("="*80)
        
        # List unindexed files from database
        files = self.list_unindexed_files(max_files=max_files)
        
        # Filter by SHA256 if specified (for full pipeline mode)
        if filter_sha256:
            filter_set = set(filter_sha256)
            filtered_files = []
            for text_key, sha256, file_record in files:
                if sha256 in filter_set:
                    filtered_files.append((text_key, sha256, file_record))
            files = filtered_files
            logger.info(f"   Filtered to {len(files)} files from process stage")
        
        if not files:
            logger.info("✨ No files to index")
            return 0, 0
        
        # Index files with progress tracking
        tracker = ProgressTracker(len(files), "Indexing")
        
        if parallel and self.max_workers > 1:
            # Parallel processing with ThreadPoolExecutor (use fewer workers for API limits)
            # Enable quiet mode for parallel processing
            self.quiet_mode = True
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all tasks
                future_to_file = {
                    executor.submit(self.index_file, text_key, sha256, file_record): (text_key, sha256)
                    for text_key, sha256, file_record in files
                }
                
                # Use tqdm for progress bar
                with tqdm(total=len(files), desc="📚 Indexing files", unit="file") as pbar:
                    for future in as_completed(future_to_file):
                        text_key, sha256 = future_to_file[future]
                        try:
                            file_id = future.result()
                            tracker.update(success=bool(file_id))
                        except Exception as e:
                            logger.error(f"   ❌ Error indexing {sha256}: {e}")
                            tracker.update(success=False)
                        
                        pbar.set_postfix_str(f"✅ {tracker.successful} | ❌ {tracker.failed}")
                        pbar.update(1)
            
            # Restore normal logging
            self.quiet_mode = False
        else:
            # Sequential processing
            with tqdm(total=len(files), desc="📚 Indexing files", unit="file") as pbar:
                for text_key, sha256, file_record in files:
                    file_id = self.index_file(text_key, sha256, file_record)
                    tracker.update(success=bool(file_id))
                    
                    if file_id:
                        pbar.set_postfix_str(f"✅ {tracker.successful} | ❌ {tracker.failed}")
                    else:
                        pbar.set_postfix_str(f"✅ {tracker.successful} | ❌ {tracker.failed}")
                    
                    pbar.update(1)
        
        # Summary
        logger.info("\n" + "="*80)
        logger.info(f"✅ Indexing complete: {tracker.successful} successful, {tracker.failed} failed")
        logger.info("="*80)
        
        return tracker.successful, tracker.failed
