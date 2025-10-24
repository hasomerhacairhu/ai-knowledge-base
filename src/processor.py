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
    s3_key_lower = s3_key.lower()
    
    # Check for explicit language hints in filename
    for code in ["hun", "eng", "ces", "slk", "pol"]:
        if f"_{code}." in s3_key_lower or f"_{code}_" in s3_key_lower:
            return [code]  # Manual hint found, use it
    
    # No manual hint found - enable unstructured's auto-detection
    return ["auto"]


def _process_file_worker(s3_key: str, config: Config, dry_run: bool, quiet_mode: bool) -> Optional[str]:
    """
    Standalone worker function for ProcessPoolExecutor.
    
    This function must be at module level (not a method) to be pickled.
    Processes a single file from objects/ to derivatives/.
    
    Args:
        s3_key: S3 object key to process
        config: Configuration object
        dry_run: Whether to run in dry-run mode
        quiet_mode: Whether to suppress per-file logging
    
    Returns:
        SHA-256 hash if successful, None otherwise
    """
    # Initialize S3 client in worker process
    s3 = S3Client(
        endpoint=config.s3_endpoint,
        access_key=config.s3_access_key,
        secret_key=config.s3_secret_key,
        bucket=config.s3_bucket,
        region=config.s3_region
    )
    
    # Set OCR agent if configured
    if config.ocr_agent:
        os.environ['OCR_AGENT'] = config.ocr_agent
    
    # Use tqdm.write for thread-safe logging with progress bars
    from tqdm import tqdm as tqdm_class
    
    def log(msg: str):
        """Thread-safe logging that works with tqdm"""
        if not quiet_mode:
            tqdm_class.write(msg)
    
    log(f"📄 Processing: {s3_key}")
    
    file_data = None
    sha256 = None
    
    try:
        # Download file
        log("   📥 Downloading...")
        file_data, object_metadata = s3.get_object(s3_key)
        
        # Compute SHA-256
        sha256 = hashlib.sha256(file_data).hexdigest()
        log(f"   🔑 SHA-256: {sha256}")
        
        # Check if already processed (lightweight check using CAS structure)
        shard1 = sha256[:2]
        shard2 = sha256[2:4]
        meta_key = f"derivatives/{shard1}/{shard2}/{sha256}/meta.json"
        
        if not dry_run and s3.object_exists(meta_key):
            log("   ⏭️  Already processed, skipping")
            return sha256
        
        if dry_run:
            log("   [DRY RUN] Would process file")
            return sha256
        
        # Get file extension from S3 key
        original_name = object_metadata.get('original-name', Path(s3_key).name)
        ext = Path(s3_key).suffix.lower()
        
        # Save to temporary file for Unstructured
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
            tmp_file.write(file_data)
            tmp_path = tmp_file.name
        
        try:
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
            s3.put_object(elements_key, elements_jsonl.encode('utf-8'), 
                               content_type='application/jsonl')
            s3.put_object(text_key, text_content.encode('utf-8'), 
                               content_type='text/plain; charset=utf-8')
            s3.put_object(meta_key, json.dumps(meta_info, indent=2).encode('utf-8'),
                               content_type='application/json')
            
            log(f"   ✅ Uploaded artifacts:")
            log(f"      - {elements_key}")
            log(f"      - {text_key}")
            log(f"      - {meta_key}")
            
            # If this was a retry, delete the failed marker
            shard1 = sha256[:2]
            failed_key = f"failed/{shard1}/{sha256}.txt"
            if s3.object_exists(failed_key):
                s3.delete_object(failed_key)
                log(f"   🗑️  Removed failed marker (successful retry)")
            
            # Source file remains in objects/ for API access - no deletion needed
            
            return sha256
        
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    except Exception as e:
        import logging
        logging.error(f"   ❌ Processing failed: {e}", exc_info=True)
        
        # Log failure with hash-based sharding (keep original in objects/)
        if not dry_run and sha256:
            try:
                shard1 = sha256[:2]
                failed_key = f"failed/{shard1}/{sha256}.txt"
                
                # Write error log (don't move the file, keep in objects/)
                error_log = {
                    "s3_key": s3_key,
                    "sha256": sha256,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "failed_at": str(datetime.now())
                }
                s3.put_object(
                    failed_key, 
                    json.dumps(error_log, indent=2).encode('utf-8'),
                    content_type='application/json'
                )
                logging.warning(f"   ⚠️  Error logged to {failed_key} (use --retry-failed to reprocess)")
            except Exception as log_error:
                logging.error(f"   Could not log failure: {log_error}")
        
        return None


class UnstructuredProcessor:
    """Process documents using Unstructured.io"""
    
    def __init__(self, config: Config, dry_run: bool = False, max_workers: int = 5, use_processes: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.max_workers = max_workers
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
    
    def list_incoming_files(self, max_files: Optional[int] = None, retry_failed: bool = False) -> List[str]:
        """
        List files in the objects/ prefix that haven't been processed
        
        Args:
            max_files: Maximum number of files to return
            retry_failed: If True, include files that previously failed processing
        
        Performance: Uses set operations instead of per-file checks.
        O(1) API calls instead of O(N) calls.
        """
        logger.info(f"🔍 Scanning objects in s3://{self.config.s3_bucket}/objects/")
        
        if self.dry_run:
            # In dry-run mode, just list files from objects/
            try:
                unprocessed = []
                for key in self.s3.list_objects('objects/'):
                    if not key.endswith('/'):
                        unprocessed.append(key)
                        if max_files and len(unprocessed) >= max_files:
                            break
                unprocessed.sort()
                logger.info(f"✅ Found {len(unprocessed)} files (dry-run mode)")
                return unprocessed
            except Exception as e:
                logger.error(f"Error listing objects: {e}")
                return []
        
        try:
            # Step 1: Build set of SHA-256 hashes from objects/
            logger.info("   📊 Listing source files...")
            source_hashes = {}  # sha256 -> s3_key
            
            for key in self.s3.list_objects('objects/'):
                if key.endswith('/'):  # Skip directories
                    continue
                
                # Extract SHA-256 from key: objects/aa/bb/aabbcc...xyz.ext
                parts = key.split('/')
                if len(parts) != 4:  # Should be: objects, aa, bb, filename
                    continue
                
                filename = parts[3]
                sha256 = Path(filename).stem
                source_hashes[sha256] = key
            
            logger.info(f"   ✅ Found {len(source_hashes)} source files")
            
            # Step 2: Build set of SHA-256 hashes from derivatives/
            logger.info("   📊 Listing processed files...")
            processed_hashes = set()
            
            for key in self.s3.list_objects('derivatives/'):
                if key.endswith('/meta.json'):
                    # Extract SHA-256 from key: derivatives/aa/bb/sha256/meta.json
                    parts = key.split('/')
                    if len(parts) >= 4:
                        sha256 = parts[3]
                        processed_hashes.add(sha256)
            
            logger.info(f"   ✅ Found {len(processed_hashes)} processed files")
            
            # Step 3: Handle retry_failed option
            failed_hashes = set()
            if retry_failed:
                logger.info("   📊 Listing failed files for retry...")
                for key in self.s3.list_objects('failed/'):
                    if key.endswith('.txt'):
                        # Extract SHA-256 from key: failed/aa/sha256.txt
                        parts = key.split('/')
                        if len(parts) >= 3:
                            sha256 = Path(parts[2]).stem
                            failed_hashes.add(sha256)
                logger.info(f"   ✅ Found {len(failed_hashes)} failed files to retry")
            
            # Step 4: Set difference to find unprocessed
            if retry_failed:
                # Include both never-processed and failed files
                unprocessed_hashes = (set(source_hashes.keys()) - processed_hashes) | failed_hashes
            else:
                # Only never-processed files (exclude failed files)
                unprocessed_hashes = set(source_hashes.keys()) - processed_hashes - failed_hashes
            
            # Step 5: Convert back to S3 keys and sort
            unprocessed_files = [source_hashes[sha256] for sha256 in unprocessed_hashes if sha256 in source_hashes]
            unprocessed_files.sort()
            
            # Step 6: Apply max_files limit
            if max_files and len(unprocessed_files) > max_files:
                unprocessed_files = unprocessed_files[:max_files]
            
            logger.info(f"✅ Found {len(unprocessed_files)} unprocessed files" + 
                       (f" (including {len(failed_hashes)} failed)" if retry_failed and failed_hashes else ""))
            return unprocessed_files
            
        except Exception as e:
            logger.error(f"Error listing objects: {e}")
            return []
    
    def download_file(self, s3_key: str) -> Tuple[bytes, Dict]:
        """Download file from S3 and return data + metadata"""
        data, metadata = self.s3.get_object(s3_key)
        return data, metadata
    
    def process_file(self, s3_key: str) -> Optional[str]:
        """
        Process a single file from objects/ to derivatives/
        
        Returns:
            SHA-256 hash if successful, None otherwise
        """
        # Use tqdm.write for thread-safe logging with progress bars
        from tqdm import tqdm as tqdm_class
        
        def log(msg: str):
            """Thread-safe logging that works with tqdm"""
            if not self.quiet_mode:
                tqdm_class.write(msg)
        
        log(f"📄 Processing: {s3_key}")
        
        file_data = None
        sha256 = None
        
        try:
            # Download file
            log("   📥 Downloading...")
            file_data, object_metadata = self.download_file(s3_key)
            
            # Compute SHA-256
            sha256 = self.compute_sha256(file_data)
            log(f"   🔑 SHA-256: {sha256}")
            
            # Check if already processed (lightweight check using CAS structure)
            shard1 = sha256[:2]
            shard2 = sha256[2:4]
            meta_key = f"derivatives/{shard1}/{shard2}/{sha256}/meta.json"
            
            if not self.dry_run and self.s3.object_exists(meta_key):
                log("   ⏭️  Already processed, skipping")
                return sha256
            
            if self.dry_run:
                log("   [DRY RUN] Would process file")
                return sha256
            
            # Get file extension from S3 key
            original_name = object_metadata.get('original-name', Path(s3_key).name)
            ext = Path(s3_key).suffix.lower()
            
            # Save to temporary file for Unstructured
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                tmp_file.write(file_data)
                tmp_path = tmp_file.name
            
            try:
                # Process with Unstructured
                log("   🔄 Processing with Unstructured...")
                
                # Detect language from filename - supports manual hints or auto-detection
                languages = _get_language_hint(s3_key)
                
                # For PDFs, use strategy="auto" with language support
                if ext == '.pdf':
                    try:
                        elements = partition(filename=tmp_path, strategy="auto", languages=languages)
                    except Exception as e:
                        logger.warning(f"   Auto strategy failed, trying hi_res: {e}")
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
                self.s3.put_object(elements_key, elements_jsonl.encode('utf-8'), 
                                   content_type='application/jsonl')
                self.s3.put_object(text_key, text_content.encode('utf-8'), 
                                   content_type='text/plain; charset=utf-8')
                self.s3.put_object(meta_key, json.dumps(meta_info, indent=2).encode('utf-8'),
                                   content_type='application/json')
                
                log(f"   ✅ Uploaded artifacts:")
                log(f"      - {elements_key}")
                log(f"      - {text_key}")
                log(f"      - {meta_key}")
                
                # If this was a retry, delete the failed marker
                shard1 = sha256[:2]
                failed_key = f"failed/{shard1}/{sha256}.txt"
                if self.s3.object_exists(failed_key):
                    self.s3.delete_object(failed_key)
                    log(f"   🗑️  Removed failed marker (successful retry)")
                
                # Source file remains in objects/ for API access - no deletion needed
                
                return sha256
            
            finally:
                # Clean up temp file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        
        except Exception as e:
            logger.error(f"   ❌ Processing failed: {e}", exc_info=True)
            
            # Log failure with hash-based sharding (keep original in objects/)
            if not self.dry_run and sha256:
                try:
                    shard1 = sha256[:2]
                    failed_key = f"failed/{shard1}/{sha256}.txt"
                    
                    # Write error log (don't move the file, keep in objects/)
                    error_log = {
                        "s3_key": s3_key,
                        "sha256": sha256,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "failed_at": str(datetime.now())
                    }
                    self.s3.put_object(
                        failed_key, 
                        json.dumps(error_log, indent=2).encode('utf-8'),
                        content_type='application/json'
                    )
                    logger.warning(f"   ⚠️  Error logged to {failed_key} (use --retry-failed to reprocess)")
                except Exception as log_error:
                    logger.error(f"   Could not log failure: {log_error}")
            
            return None
    
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
        
        # List incoming files
        files = self.list_incoming_files(max_files=max_files, retry_failed=retry_failed)
        
        # Filter by SHA256 if specified (for full pipeline mode)
        if filter_sha256:
            filter_set = set(filter_sha256)
            filtered_files = []
            for s3_key in files:
                # Extract SHA256 from key: objects/aa/bb/sha256.ext
                sha256 = Path(s3_key).stem
                if sha256 in filter_set:
                    filtered_files.append(s3_key)
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
                        executor.submit(_process_file_worker, s3_key, self.config, self.dry_run, self.quiet_mode): s3_key 
                        for s3_key in files
                    }
                else:
                    # For ThreadPoolExecutor, use the instance method
                    future_to_key = {
                        executor.submit(self.process_file, s3_key): s3_key 
                        for s3_key in files
                    }
                
                # Use tqdm for progress bar
                with tqdm(total=len(files), desc="🔄 Processing files", unit="file") as pbar:
                    for future in as_completed(future_to_key):
                        s3_key = future_to_key[future]
                        try:
                            sha256 = future.result()
                            tracker.update(success=bool(sha256))
                            if sha256:
                                processed_sha256_hashes.append(sha256)
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
                for s3_key in files:
                    sha256 = self.process_file(s3_key)
                    tracker.update(success=bool(sha256))
                    
                    if sha256:
                        processed_sha256_hashes.append(sha256)
                        pbar.set_postfix_str(f"✅ {tracker.successful} | ❌ {tracker.failed}")
                    else:
                        pbar.set_postfix_str(f"✅ {tracker.successful} | ❌ {tracker.failed}")
                    
                    pbar.update(1)
        
        # Summary
        logger.info("\n" + "="*80)
        logger.info(f"✅ Processing complete: {tracker.successful} successful, {tracker.failed} failed")
        logger.info("="*80)
        
        return tracker.successful, tracker.failed, processed_sha256_hashes
