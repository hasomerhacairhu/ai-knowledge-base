"""OpenAI Vector Store indexer"""

import json
import io
from datetime import datetime
from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI
from tqdm import tqdm

from .config import Config
from .utils import S3Client, setup_logging, ProgressTracker

logger = setup_logging(__name__)


class VectorStoreIndexer:
    """Index processed text files into OpenAI Vector Store"""
    
    def __init__(self, config: Config, dry_run: bool = False, max_workers: int = 3):
        self.config = config
        self.dry_run = dry_run
        self.max_workers = max_workers
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
        
        # Track indexed files with hash-based sharding
        self.indexed_marker_prefix = "indexed/"
    
    def mark_as_indexing(self, sha256: str):
        """Mark a file as currently being indexed (temporary marker)"""
        if self.dry_run:
            return
        
        shard1 = sha256[:2]
        marker_key = f"{self.indexed_marker_prefix}{shard1}/{sha256}.indexing"
        marker_data = {
            "sha256": sha256,
            "started_at": str(datetime.now())
        }
        
        self.s3.put_object(
            marker_key,
            json.dumps(marker_data, indent=2).encode('utf-8'),
            content_type='application/json'
        )
    
    def mark_as_indexed(self, sha256: str, file_id: str):
        """Mark a file as successfully indexed (atomic rename from .indexing to .indexed)"""
        if self.dry_run:
            logger.info(f"   [DRY RUN] Would mark as indexed: {sha256}")
            return
        
        shard1 = sha256[:2]
        indexing_key = f"{self.indexed_marker_prefix}{shard1}/{sha256}.indexing"
        indexed_key = f"{self.indexed_marker_prefix}{shard1}/{sha256}.indexed"
        
        marker_data = {
            "sha256": sha256,
            "openai_file_id": file_id,
            "vector_store_id": self.config.vector_store_id,
            "indexed_at": str(datetime.now())
        }
        
        # Write the final .indexed marker
        self.s3.put_object(
            indexed_key,
            json.dumps(marker_data, indent=2).encode('utf-8'),
            content_type='application/json'
        )
        
        # Clean up the temporary .indexing marker
        try:
            self.s3.delete_object(indexing_key)
        except Exception:
            pass  # Ignore if .indexing marker doesn't exist
    
    def list_unindexed_files(self, max_files: Optional[int] = None) -> List[Tuple[str, str, dict]]:
        """
        List processed text files that haven't been indexed yet
        
        Performance: Uses set operations instead of per-file checks.
        O(1) API calls instead of O(N) calls.
        
        Returns:
            List of tuples: (text_key, sha256, metadata_dict)
        """
        logger.info(f"🔍 Scanning derivatives files in s3://{self.config.s3_bucket}/derivatives/")
        
        try:
            # Step 1: Build set of SHA-256 hashes from indexed/ markers
            logger.info("   📊 Listing indexed files...")
            indexed_hashes = set()
            indexing_hashes = set()  # Track files currently being indexed
            
            for key in self.s3.list_objects(self.indexed_marker_prefix):
                if key.endswith('.indexed'):
                    # Extract SHA-256 from key: indexed/aa/sha256.indexed
                    parts = key.split('/')
                    if len(parts) >= 3:
                        filename = parts[-1]  # sha256.indexed
                        sha256 = filename.replace('.indexed', '')
                        indexed_hashes.add(sha256)
                elif key.endswith('.indexing'):
                    # Extract SHA-256 from key: indexed/aa/sha256.indexing
                    parts = key.split('/')
                    if len(parts) >= 3:
                        filename = parts[-1]  # sha256.indexing
                        sha256 = filename.replace('.indexing', '')
                        indexing_hashes.add(sha256)
            
            logger.info(f"   ✅ Found {len(indexed_hashes)} indexed files")
            if indexing_hashes:
                logger.info(f"   ⚠️  Found {len(indexing_hashes)} files with .indexing markers (may be stale)")
            
            # Step 2: List all derivatives and filter out indexed/indexing ones
            logger.info("   � Scanning derivatives...")
            unindexed = []
            
            for key in self.s3.list_objects('derivatives/'):
                if not key.endswith('/meta.json'):
                    continue
                
                # Load metadata to get SHA-256
                try:
                    meta_data, _ = self.s3.get_object(key)
                    metadata = json.loads(meta_data.decode('utf-8'))
                    sha256 = metadata.get('sha256')
                    
                    if not sha256:
                        continue
                    
                    # Check if already indexed or currently being indexed (in-memory set lookup)
                    if sha256 in indexed_hashes or sha256 in indexing_hashes:
                        continue
                    
                    # Build text key from meta key
                    # meta key: derivatives/aa/bb/sha256/meta.json
                    # text key: derivatives/aa/bb/sha256/text.txt
                    text_key = key.replace('/meta.json', '/text.txt')
                    
                    unindexed.append((text_key, sha256, metadata))
                    
                    if max_files and len(unindexed) >= max_files:
                        break
                        
                except Exception as e:
                    logger.warning(f"Could not load metadata from {key}: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error listing derivatives files: {e}")
            return []
        
        logger.info(f"✅ Found {len(unindexed)} unindexed files")
        return unindexed
    
    def index_file(self, text_key: str, sha256: str, metadata: dict) -> Optional[str]:
        """
        Index a single text file to Vector Store
        
        Returns:
            OpenAI file ID if successful, None otherwise
        """
        def log(msg: str):
            if not self.quiet_mode:
                logger.info(msg)
        
        log(f"📄 Indexing: {sha256}")
        log(f"   Original: {metadata.get('original_name', 'unknown')}")
        
        if self.dry_run:
            log(f"   [DRY RUN] Would upload to Vector Store: {self.config.vector_store_id}")
            return f"file-{sha256[:8]}-dryrun"
        
        try:
            # Create temporary .indexing marker FIRST (prevents race condition)
            log("   🔒 Creating indexing marker...")
            self.mark_as_indexing(sha256)
            
            # Download text content
            log("   📥 Downloading text...")
            text_content, _ = self.s3.get_object(text_key)
            
            # Upload to OpenAI
            log("   📤 Uploading to OpenAI...")
            
            # Create a file object
            file_obj = io.BytesIO(text_content)
            file_obj.name = f"{sha256}.txt"
            
            # Upload file
            file_response = self.openai_client.files.create(
                file=file_obj,
                purpose='assistants'
            )
            
            file_id = file_response.id
            log(f"   ✅ Uploaded file: {file_id}")
            
            # Add to Vector Store
            log(f"   📚 Adding to Vector Store: {self.config.vector_store_id}")
            
            # Prepare metadata for Vector Store (minimal, avoid duplication)
            vs_metadata = {
                "sha256": sha256,
                "source": "drive",
                "extension": metadata.get('extension', ''),
                "pipeline": "unstructured:auto"
            }
            
            self.openai_client.beta.vector_stores.files.create(
                vector_store_id=self.config.vector_store_id,
                file_id=file_id
            )
            
            log("   ✅ Added to Vector Store")
            
            # Mark as indexed (atomically replaces .indexing with .indexed)
            self.mark_as_indexed(sha256, file_id)
            
            return file_id
        
        except Exception as e:
            logger.error(f"   Error indexing file: {e}", exc_info=True)
            
            # Clean up temporary .indexing marker on failure
            if not self.dry_run:
                try:
                    shard1 = sha256[:2]
                    indexing_key = f"{self.indexed_marker_prefix}{shard1}/{sha256}.indexing"
                    self.s3.delete_object(indexing_key)
                    logger.info(f"   🧹 Cleaned up .indexing marker")
                except Exception:
                    pass
            
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
        
        # List unindexed files
        files = self.list_unindexed_files(max_files=max_files)
        
        # Filter by SHA256 if specified (for full pipeline mode)
        if filter_sha256:
            filter_set = set(filter_sha256)
            filtered_files = []
            for text_key, sha256, metadata in files:
                if sha256 in filter_set:
                    filtered_files.append((text_key, sha256, metadata))
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
                    executor.submit(self.index_file, text_key, sha256, metadata): (text_key, sha256)
                    for text_key, sha256, metadata in files
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
                for text_key, sha256, metadata in files:
                    file_id = self.index_file(text_key, sha256, metadata)
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
