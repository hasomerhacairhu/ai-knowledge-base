"""Unstructured processing pipeline for document normalization"""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import tempfile
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed

from tqdm import tqdm
from unstructured.partition.auto import partition

from .config import Config
from .database import Database, FileStatus
from .utils import S3Client, setup_logging, ProgressTracker

logger = setup_logging(__name__)


def _get_language_hint(s3_key: str) -> List[str]:
    """
    Detect language hint from filename for OCR optimization.
    
    Checks for manual language codes in the filename (e.g., document_hun.pdf, report_pol_2025.pdf).
    If no manual hint is found, returns ["auto"] to enable unstructured's built-in auto-detection.
    
    Supported manual hints:
    - _hun: Hungarian
    - _eng: English
    - _ces: Czech
    - _slk: Slovak
    - _pol: Polish
    
    Args:
        s3_key: S3 object key (filename)
    
    Returns:
        List of language codes for Tesseract OCR, or ["auto"] for auto-detection
    """
    import re
    
    s3_key_lower = s3_key.lower()
    
    # Check for explicit language hints in filename using robust regex
    # Match language codes surrounded by underscores, dashes, or at word boundaries
    # Handles: document_hun.pdf, file-eng-final.pdf, report_HUN_2025.pdf, etc.
    pattern = r'[_\-](' + '|'.join(['hun', 'eng', 'ces', 'slk', 'pol']) + r')[_\-\.]'
    match = re.search(pattern, s3_key_lower)
    
    if match:
        return [match.group(1)]  # Manual hint found, use it
    
    # No manual hint found - enable unstructured's auto-detection
    return ["auto"]


def _process_single_file(
    sha256: str, 
    s3_key: str, 
    s3_client, 
    database: Database, 
    dry_run: bool, 
    quiet_mode: bool
) -> Optional[str]:
    """
    Shared processing logic for both ProcessPoolExecutor and ThreadPoolExecutor.
    
    This function contains the core file processing logic that was previously
    duplicated in _process_file_worker and UnstructuredProcessor.process_file.
    
    Args:
        sha256: SHA-256 hash of the file
        s3_key: S3 object key to process
        s3_client: S3Client instance
        database: Database instance
        dry_run: Whether to run in dry-run mode
        quiet_mode: Whether to suppress per-file logging
    
    Returns:
        SHA-256 hash if successful, None otherwise
    """
    # Use tqdm.write for thread-safe logging with progress bars
    from tqdm import tqdm as tqdm_class
    
    def log(msg: str):
        """Thread-safe logging that works with tqdm"""
        if not quiet_mode:
            tqdm_class.write(msg)
    
    log(f"📄 Processing: {s3_key}")
    log(f"   🔑 SHA-256: {sha256}")
    
    try:
        # Check database for current status
        file_record = database.get_file_by_sha256(sha256)
        
        # If already processed, skip
        if file_record and file_record["status"] in ["processed", "indexing", "indexed"]:
            log(f"   ⏭️  Already processed (status: {file_record['status']}), skipping")
            return sha256
        
        # Mark as PROCESSING in database
        if not dry_run:
            database.upsert_file(
                sha256=sha256,
                s3_key=s3_key,
                status=FileStatus.PROCESSING
            )
        
        if dry_run:
            log("   [DRY RUN] Would process file")
            return sha256
        
        # Download file - STREAM directly to temp file (memory-efficient)
        log("   📥 Downloading...")
        
        # Get file extension from S3 key
        ext = Path(s3_key).suffix.lower()
        
        # Create temp file
        tmp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp_path = tmp_file.name
        
        try:
            # Stream from S3 directly to temp file (no memory buffering)
            stream, object_metadata = s3_client.get_object_stream(s3_key)
            
            # Write in chunks to avoid loading entire file into memory
            for chunk in stream.iter_chunks(chunk_size=8192):
                tmp_file.write(chunk)
            tmp_file.close()
            
            # Get original name from metadata
            original_name = object_metadata.get('original-name', Path(s3_key).name)
            
            # Process with Unstructured
            log("   🔄 Processing with Unstructured...")
            
            # Detect language from filename - supports manual hints or auto-detection
            languages = _get_language_hint(s3_key)
            
            # For PDFs, use strategy="auto" with language support
            if ext == '.pdf':
                try:
                    elements = partition(filename=tmp_path, strategy="auto", languages=languages)
                except Exception as e:
                    log(f"   Auto strategy failed, trying hi_res: {e}")
                    elements = partition(filename=tmp_path, strategy="hi_res", languages=languages)
            else:
                elements = partition(filename=tmp_path)
            
            log(f"   ✅ Extracted {len(elements)} elements")
            
            # Generate artifacts
            elements_jsonl = "\n".join(el.to_dict().__str__() for el in elements)
            text_content = "\n\n".join(str(el) for el in elements)
            
            # Minimal meta.json - avoid duplicating S3 metadata
            meta_info = {
                "sha256": sha256,
                "extension": ext,
                "element_count": len(elements),
                "text_length": len(text_content),
                "processed_at": str(datetime.now())
            }
            
            # Upload artifacts to derivatives/ with hash-based sharding
            shard1 = sha256[:2]
            shard2 = sha256[2:4]
            elements_key = f"derivatives/{shard1}/{shard2}/{sha256}/elements.jsonl"
            text_key = f"derivatives/{shard1}/{shard2}/{sha256}/text.txt"
            meta_key = f"derivatives/{shard1}/{shard2}/{sha256}/meta.json"
            
            log("   📤 Uploading artifacts...")
            
            # Upload derivatives only (source already exists in objects/)
            s3_client.put_object(elements_key, elements_jsonl.encode('utf-8'), 
                               content_type='application/jsonl')
            s3_client.put_object(text_key, text_content.encode('utf-8'), 
                               content_type='text/plain; charset=utf-8')
            s3_client.put_object(meta_key, json.dumps(meta_info, indent=2).encode('utf-8'),
                               content_type='application/json')
            
            log(f"   ✅ Uploaded artifacts:")
            log(f"      - {elements_key}")
            log(f"      - {text_key}")
            log(f"      - {meta_key}")
            
            # Mark as PROCESSED in database
            database.upsert_file(
                sha256=sha256,
                s3_key=s3_key,
                status=FileStatus.PROCESSED,
                extension=ext
            )
            
            return sha256
        
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    except Exception as e:
        import logging
        logging.error(f"   ❌ Processing failed: {e}", exc_info=True)
        
        # Mark as FAILED_PROCESS in database
        if not dry_run:
            database.upsert_file(
                sha256=sha256,
                s3_key=s3_key,
                status=FileStatus.FAILED_PROCESS,
                error_message=str(e),
                error_type=type(e).__name__
            )
            logging.warning(f"   ⚠️  Marked as failed in database (use --retry-failed to reprocess)")
        
        return None


def _process_file_worker(sha256: str, s3_key: str, config: Config, db_path: str, dry_run: bool, quiet_mode: bool) -> Optional[str]:
    """
    Standalone worker function for ProcessPoolExecutor.
    
    This function must be at module level (not a method) to be pickled.
    It initializes S3 and database clients and delegates to the shared processing logic.
    
    Args:
        sha256: SHA-256 hash of the file
        s3_key: S3 object key to process
        config: Configuration object
        db_path: Path to SQLite database
        dry_run: Whether to run in dry-run mode
        quiet_mode: Whether to suppress per-file logging
    
    Returns:
        SHA-256 hash if successful, None otherwise
    """
    # Initialize S3 client and database in worker process
    s3 = S3Client(
        endpoint=config.s3_endpoint,
        access_key=config.s3_access_key,
        secret_key=config.s3_secret_key,
        bucket=config.s3_bucket,
        region=config.s3_region
    )
    
    database = Database(db_path)
    
    # Set OCR agent if configured
    if config.ocr_agent:
        os.environ['OCR_AGENT'] = config.ocr_agent
    
    # Delegate to shared processing logic
    return _process_single_file(sha256, s3_key, s3, database, dry_run, quiet_mode)


class UnstructuredProcessor:
    """Process documents using Unstructured.io"""
    
    def __init__(self, config: Config, database: Database, dry_run: bool = False, max_workers: Optional[int] = None, use_processes: bool = False):
        self.config = config
        self.database = database
        self.dry_run = dry_run
        self.max_workers = max_workers or config.processor_max_workers
        self.use_processes = use_processes  # Use ProcessPoolExecutor for CPU-bound tasks
        self.quiet_mode = False  # Set to True to suppress per-file logging in parallel mode
        
        # Initialize S3 client with connection pooling
        self.s3 = S3Client(
            endpoint=config.s3_endpoint,
            access_key=config.s3_access_key,
            secret_key=config.s3_secret_key,
            bucket=config.s3_bucket,
            region=config.s3_region
        )
        
        # Set OCR agent if configured
        if config.ocr_agent:
            os.environ['OCR_AGENT'] = config.ocr_agent
    
    def compute_sha256(self, data: bytes) -> str:
        """Compute SHA-256 hash of file data"""
        return hashlib.sha256(data).hexdigest()
    
    def list_incoming_files(self, max_files: Optional[int] = None, retry_failed: bool = False) -> List[Tuple[str, str]]:
        """
        List files ready for processing using database queries (O(1) lookup)
        
        Args:
            max_files: Maximum number of files to return
            retry_failed: If True, include files that previously failed processing
        
        Returns:
            List of tuples: (s3_key, sha256)
        """
        logger.info(f"🔍 Querying database for files ready to process...")
        
        try:
            if retry_failed:
                # Get files with FAILED_PROCESS status
                files = self.database.get_files_by_status(FileStatus.FAILED_PROCESS, limit=max_files)
                logger.info(f"✅ Found {len(files)} failed files to retry")
            else:
                # Get files with SYNCED status
                files = self.database.get_files_for_processing(limit=max_files)
                logger.info(f"✅ Found {len(files)} unprocessed files")
            
            # Convert to expected format: (s3_key, sha256)
            result = [(file["s3_key"], file["sha256"]) for file in files]
            return result
        
        except Exception as e:
            logger.error(f"Error querying database: {e}")
            return []
    
    def download_file(self, s3_key: str) -> Tuple[str, Dict, str]:
        """
        Download file from S3 directly to temp file (memory-efficient streaming)
        
        Returns:
            Tuple of (tmp_path, metadata, extension)
        """
        # Get file extension from S3 key
        ext = Path(s3_key).suffix.lower()
        
        # Create temp file
        tmp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp_path = tmp_file.name
        
        # Stream from S3 directly to temp file (no memory buffering)
        stream, metadata = self.s3.get_object_stream(s3_key)
        
        # Write in chunks to avoid loading entire file into memory
        for chunk in stream.iter_chunks(chunk_size=8192):
            tmp_file.write(chunk)
        tmp_file.close()
        
        return tmp_path, metadata, ext
    
    def process_file(self, s3_key: str, sha256: str) -> Optional[str]:
        """
        Process a single file from objects/ to derivatives/
        
        This is a thin wrapper that delegates to the shared processing logic.
        
        Args:
            s3_key: S3 object key
            sha256: SHA-256 hash of the file
        
        Returns:
            SHA-256 hash if successful, None otherwise
        """
        # Delegate to shared processing logic
        return _process_single_file(
            sha256, s3_key, self.s3, self.database, self.dry_run, self.quiet_mode
        )
    
    def process_batch(self, max_files: Optional[int] = None, parallel: bool = True, retry_failed: bool = False, filter_sha256: Optional[List[str]] = None) -> Tuple[int, int, List[str]]:
        """
        Process a batch of files from objects/
        
        Args:
            max_files: Maximum number of files to process
            parallel: Use parallel processing (default: True)
            retry_failed: If True, retry previously failed files
            filter_sha256: Optional list of SHA256 hashes to process (for full pipeline)
        
        Returns:
            Tuple of (successful_count, failed_count, list_of_processed_sha256_hashes)
        """
        logger.info("="*80)
        logger.info("🔄 Starting Unstructured Processing")
        if self.dry_run:
            logger.info("   [DRY RUN MODE - No changes will be made]")
        if parallel:
            executor_type = "ProcessPoolExecutor" if self.use_processes else "ThreadPoolExecutor"
            logger.info(f"   [PARALLEL MODE - {self.max_workers} workers using {executor_type}]")
            if self.use_processes:
                logger.info("   [CPU-OPTIMIZED - Better for OCR-heavy workloads]")
        if retry_failed:
            logger.info("   [RETRY MODE - Including previously failed files]")
        if filter_sha256:
            logger.info(f"   [FILTERED MODE - Processing {len(filter_sha256)} specific files from sync stage]")
        logger.info("="*80)
        
        # List incoming files (returns tuples of (s3_key, sha256))
        files = self.list_incoming_files(max_files=max_files, retry_failed=retry_failed)
        
        # Filter by SHA256 if specified (for full pipeline mode)
        if filter_sha256:
            filter_set = set(filter_sha256)
            filtered_files = []
            for s3_key, sha256 in files:
                if sha256 in filter_set:
                    filtered_files.append((s3_key, sha256))
            files = filtered_files
            logger.info(f"   Filtered to {len(files)} files from sync stage")
        
        if not files:
            logger.info("✨ No files to process")
            return 0, 0, []
        
        # Process files with progress tracking
        tracker = ProgressTracker(len(files), "Processing")
        processed_sha256_hashes = []  # Track successfully processed SHA256 hashes
        
        if parallel and self.max_workers > 1:
            # Choose executor based on use_processes flag
            ExecutorClass = ProcessPoolExecutor if self.use_processes else ThreadPoolExecutor
            
            # Enable quiet mode to reduce console spam
            self.quiet_mode = True
            
            with ExecutorClass(max_workers=self.max_workers) as executor:
                # Submit all tasks
                if self.use_processes:
                    # For ProcessPoolExecutor, use the standalone worker function
                    future_to_key = {
                        executor.submit(_process_file_worker, sha256, s3_key, self.config, self.database.db_path, self.dry_run, self.quiet_mode): (s3_key, sha256)
                        for s3_key, sha256 in files
                    }
                else:
                    # For ThreadPoolExecutor, use the instance method
                    future_to_key = {
                        executor.submit(self.process_file, s3_key, sha256): (s3_key, sha256)
                        for s3_key, sha256 in files
                    }
                
                # Use tqdm for progress bar
                with tqdm(total=len(files), desc="🔄 Processing files", unit="file") as pbar:
                    for future in as_completed(future_to_key):
                        s3_key, sha256 = future_to_key[future]
                        try:
                            result_sha256 = future.result()
                            tracker.update(success=bool(result_sha256))
                            if result_sha256:
                                processed_sha256_hashes.append(result_sha256)
                        except Exception as e:
                            logger.error(f"   ❌ Error processing {s3_key}: {e}")
                            tracker.update(success=False)
                        
                        skipped = tracker.successful - (tracker.current - tracker.failed)
                        pbar.set_postfix_str(f"✅ {tracker.successful} | ❌ {tracker.failed}")
                        pbar.update(1)
            
            # Restore normal logging
            self.quiet_mode = False
        else:
            # Sequential processing
            with tqdm(total=len(files), desc="🔄 Processing files", unit="file") as pbar:
                for s3_key, sha256 in files:
                    result_sha256 = self.process_file(s3_key, sha256)
                    tracker.update(success=bool(result_sha256))
                    
                    if result_sha256:
                        processed_sha256_hashes.append(result_sha256)
                        pbar.set_postfix_str(f"✅ {tracker.successful} | ❌ {tracker.failed}")
                    else:
                        pbar.set_postfix_str(f"✅ {tracker.successful} | ❌ {tracker.failed}")
                    
                    pbar.update(1)
        
        # Summary
        logger.info("\n" + "="*80)
        logger.info(f"✅ Processing complete: {tracker.successful} successful, {tracker.failed} failed")
        logger.info("="*80)
        
        return tracker.successful, tracker.failed, processed_sha256_hashes
