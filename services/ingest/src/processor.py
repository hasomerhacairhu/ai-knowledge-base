"""Unstructured processing pipeline for document normalization"""

import hashlib
import json
import os
import warnings
import sys
import gc
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import tempfile
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from io import StringIO

from tqdm import tqdm
from unstructured.partition.auto import partition

from .config import Config
from .database import Database, FileStatus
from .utils import S3Client, setup_logging, ProgressTracker

# Suppress deprecation warnings from unstructured library
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', message='.*max_size.*deprecated.*')
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', message='.*No languages specified.*')

# Force Tesseract OCR (hardcoded - other OCR engines not supported)
os.environ["OCR_AGENT"] = "unstructured.partition.utils.ocr_models.tesseract_ocr.OCRAgentTesseract"

# Suppress Tesseract warnings
os.environ["TESSDATA_PREFIX"] = os.environ.get("TESSDATA_PREFIX", "/opt/homebrew/share/tessdata/")
os.environ["OMP_THREAD_LIMIT"] = "1"  # Reduce Tesseract thread spam

# AGGRESSIVE: Monkey patch the print statement in unstructured.partition.pdf
# that outputs "Warning: No languages specified, defaulting to English."
import builtins
_original_print = builtins.print
def _filtered_print(*args, **kwargs):
    """Filter out the annoying language warning from unstructured"""
    msg = ' '.join(str(arg) for arg in args)
    if 'No languages specified' not in msg and 'defaulting to English' not in msg:
        _original_print(*args, **kwargs)
builtins.print = _filtered_print

logger = setup_logging(__name__)


class DeprecationWarningFilter:
    """Filter to suppress deprecation warnings and other noise in stderr"""
    def __init__(self, stream):
        self.stream = stream
        self._suppress = [
            'deprecated', 
            'max_size', 
            'backward compatibility', 
            'deprecation',
            'no languages specified',
            'defaulting to english'
        ]
    
    def write(self, text):
        # Only write if text doesn't contain suppressed keywords
        # Check if stream is still open to avoid "I/O operation on closed file" errors
        if not any(keyword in text.lower() for keyword in self._suppress):
            try:
                if not self.stream.closed:
                    self.stream.write(text)
            except (ValueError, AttributeError):
                # Stream is closed or doesn't support closed attribute, silently ignore
                pass
    
    def flush(self):
        try:
            if not self.stream.closed:
                self.stream.flush()
        except (ValueError, AttributeError):
            pass
    
    def fileno(self):
        return self.stream.fileno() if hasattr(self.stream, 'fileno') else None


def _get_language_hint(s3_key: str) -> str:
    """
    Detect language hint from filename for OCR optimization (Tesseract).
    
    Checks for manual language codes in the filename (e.g., document_hun.pdf, report_pol_2025.pdf).
    If no manual hint is found, returns "eng+hun" for English+Hungarian multilingual recognition.
    
    Tesseract language codes (3-letter ISO 639-2):
    - eng: English
    - hun: Hungarian (magyar)
    - ces: Czech
    - slk: Slovak
    - pol: Polish
    - deu: German
    - fra: French
    - spa: Spanish
    - ita: Italian
    - ron: Romanian
    - Multiple languages: Use + separator (e.g., "eng+hun+ces")
    
    Args:
        s3_key: S3 object key (filename)
    
    Returns:
        Language code string for Tesseract (e.g., "eng+hun")
    """
    import re
    
    s3_key_lower = s3_key.lower()
    
    # Map common filename language hints to Tesseract 3-letter codes
    # Tesseract uses ISO 639-2 codes
    lang_map = {
        'hun': 'hun',  # Hungarian
        'magyar': 'hun',  # Hungarian native name
        'eng': 'eng',  # English
        'english': 'eng',
        'ces': 'ces',  # Czech
        'czech': 'ces',
        'slk': 'slk',  # Slovak
        'slovak': 'slk',
        'pol': 'pol',  # Polish
        'polish': 'pol',
        'deu': 'deu',  # German
        'german': 'deu',
        'fra': 'fra',  # French
        'french': 'fra',
        'spa': 'spa',  # Spanish
        'spanish': 'spa',
        'ita': 'ita',  # Italian
        'italian': 'ita',
        'ron': 'ron',  # Romanian
        'romanian': 'ron',
    }
    
    # Check for explicit language hints in filename using robust regex
    pattern = r'[_\-](' + '|'.join(lang_map.keys()) + r')[_\-\.]'
    match = re.search(pattern, s3_key_lower)
    
    if match:
        detected_code = match.group(1)
        tesseract_lang = lang_map[detected_code]
        return tesseract_lang
    
    # No manual hint found - use English+Hungarian as default
    # Tesseract supports multiple languages simultaneously with + separator
    return "eng+hun"


def _partition_in_process(args_tuple: tuple) -> List:
    """
    Worker function to partition documents in a separate process.
    Must be at module level for pickling.
    
    Args:
        args_tuple: Tuple of (path, extension, lang) to avoid pickling issues
    
    Returns:
        List of document elements
    """
    path, extension, lang = args_tuple
    
    import os
    import sys
    import warnings
    
    # Force Tesseract OCR in worker process (hardcoded)
    os.environ["OCR_AGENT"] = "unstructured.partition.utils.ocr_models.tesseract_ocr.OCRAgentTesseract"
    
    # Suppress warnings in worker
    warnings.filterwarnings('ignore')
    
    # Suppress stderr output (warnings that bypass Python warnings system)
    class StderrFilter:
        def __init__(self, stream):
            self.stream = stream
            self._suppress = ['no languages specified', 'defaulting to english', 'warning:']
        def write(self, text):
            if not any(keyword in text.lower() for keyword in self._suppress):
                self.stream.write(text)
        def flush(self):
            self.stream.flush()
    
    old_stderr = sys.stderr
    sys.stderr = StderrFilter(old_stderr)
    
    try:
        # Import after env is set
        from unstructured.partition.auto import partition
        from unstructured.partition.pdf import partition_pdf
        
        if extension == '.pdf':
            # Use smart PDF partitioning (fast → OCR fallback)
            fast_elements = partition_pdf(path, strategy="fast", include_page_breaks=True)
            total_chars = sum(len(getattr(e, "text", "") or "") for e in fast_elements)
            pages = 1 + sum(1 for e in fast_elements if getattr(e, "category", "") == "PageBreak")
            
            if total_chars >= 200 * max(1, pages):
                return fast_elements
            
            # Fallback to OCR with Tesseract
            # Split language string if needed (e.g., "eng+hun" -> ["eng", "hun"])
            lang_list = lang.split('+') if isinstance(lang, str) and '+' in lang else ([lang] if isinstance(lang, str) else lang)
            
            return partition_pdf(
                path,
                strategy="hi_res",  # Use hi_res strategy which includes OCR
                languages=lang_list,  # List of language codes (e.g., ["eng", "hun"])
                infer_table_structure=True,  # Better structure detection
                include_page_breaks=True
            )
        else:
            # Non-PDF files use standard partitioning
            return partition(filename=path)
    finally:
        sys.stderr = old_stderr


def _partition_pdf_smart(tmp_path: str, language: str, min_chars_per_page: int = 200):
    """
    Smart PDF partitioning: fast text extraction with OCR fallback.
    
    Strategy:
    1. Try fast extraction first (cheap, no OCR)
    2. If text density is low, fallback to OCR with Tesseract
    3. Never use hi_res (too slow, unnecessary for most documents)
    
    Args:
        tmp_path: Path to PDF file
        language: Language code for OCR (e.g., "eng+hun", "eng")
        min_chars_per_page: Minimum characters per page to consider "good" extraction
    
    Returns:
        List of document elements
    """
    from unstructured.partition.pdf import partition_pdf
    
    # Suppress stderr during partitioning
    old_stderr = sys.stderr
    sys.stderr = DeprecationWarningFilter(old_stderr)
    
    try:
        # 1) Fast text extraction (no OCR)
        fast_elements = partition_pdf(
            tmp_path, 
            strategy="fast",
            include_page_breaks=True
        )
        
        # Calculate text density
        total_chars = sum(len(getattr(e, "text", "") or "") for e in fast_elements)
        pages = 1 + sum(1 for e in fast_elements if getattr(e, "category", "") == "PageBreak")
        chars_per_page = total_chars / max(1, pages)
        
        # If enough real text, use fast result
        if chars_per_page >= min_chars_per_page:
            return fast_elements
        
        # 2) Low text density - fallback to OCR with Tesseract
        # Tesseract supports multiple languages with + separator (e.g., "eng+hun")
        # But unstructured's languages parameter needs a list of individual codes
        lang_list = language.split('+') if '+' in language else [language]
        
        ocr_elements = partition_pdf(
            tmp_path,
            strategy="hi_res",  # Use hi_res strategy which includes OCR
            languages=lang_list,  # List of language codes (e.g., ["eng", "hun"])
            infer_table_structure=True,  # Better structure detection
            include_page_breaks=True
        )
        
        return ocr_elements
        
    finally:
        sys.stderr = old_stderr


def _process_with_timeout(tmp_path: str, ext: str, language: str, timeout: int = 300) -> List:
    """
    Process document with hard timeout using ProcessPoolExecutor.
    Ensures that hung Tesseract/OCR processes are terminated.
    
    Args:
        tmp_path: Path to temporary file
        ext: File extension
        language: Language code for OCR (e.g., "eng+hun", "eng")
        timeout: Timeout in seconds (default: 300s = 5 minutes)
    
    Returns:
        List of document elements
    
    Raises:
        TimeoutError: If processing exceeds timeout
    """
    from concurrent.futures import ProcessPoolExecutor, TimeoutError as FutureTimeoutError
    
    # Use 5 minutes timeout for all file types (complex DOCX files with images can take time)
    actual_timeout = timeout
    
    with ProcessPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_partition_in_process, (tmp_path, ext, language))
        try:
            return future.result(timeout=actual_timeout)
        except FutureTimeoutError:
            # Cancel the future and shutdown executor forcefully
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise TimeoutError(f"Processing exceeded {actual_timeout}s timeout - file may be corrupted or too complex")


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
        
        # Mark as PROCESSING in database (clear any previous errors)
        if not dry_run:
            database.upsert_file(
                sha256=sha256,
                s3_key=s3_key,
                status=FileStatus.PROCESSING,
                error_message="",  # Clear previous errors when retrying
                error_type=""
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
            tmp_file.flush()  # Ensure all data is written to disk
            os.fsync(tmp_file.fileno())  # Force OS to write to disk
            tmp_file.close()
            
            # Get original name from metadata
            original_name = object_metadata.get('original-name', Path(s3_key).name)
            
            # Process with Unstructured (fast → OCR fallback strategy)
            log("   🔄 Processing with Unstructured...")
            
            # Detect language from filename
            language = _get_language_hint(s3_key)
            
            # Initialize processing metadata
            processing_strategy = "standard"
            chars_per_page = None
            
            # Process based on file type with timeout protection
            if ext == '.pdf':
                # PDF: Use fast → OCR fallback WITH TIMEOUT
                from unstructured.partition.pdf import partition_pdf
                
                # Suppress stderr warnings during PDF processing
                old_stderr = sys.stderr
                sys.stderr = DeprecationWarningFilter(old_stderr)
                
                try:
                    # 1) Try fast extraction first (no OCR) - usually quick
                    fast_elements = partition_pdf(tmp_path, strategy="fast", include_page_breaks=True)
                    total_chars = sum(len(getattr(e, "text", "") or "") for e in fast_elements)
                    pages = 1 + sum(1 for e in fast_elements if getattr(e, "category", "") == "PageBreak")
                    chars_per_page = total_chars / max(1, pages)
                    
                    if chars_per_page >= 200:
                        # Good text density - use fast result
                        elements = fast_elements
                        processing_strategy = "fast"
                        log(f"   ✅ Fast extraction: {total_chars} chars, {pages} pages")
                    else:
                        # Low text density - fallback to OCR WITH TIMEOUT
                        processing_strategy = "ocr"
                        log(f"   ⚠️  Low text density ({chars_per_page:.0f} chars/page), using OCR...")
                        
                        # Use timeout protection for OCR (Tesseract can hang)
                        try:
                            elements = _process_with_timeout(tmp_path, ext, language, timeout=300)
                            log(f"   ✅ OCR completed successfully")
                        except TimeoutError as te:
                            log(f"   ⚠️  OCR timeout after 300s, falling back to fast extraction")
                            elements = fast_elements  # Use fast extraction even if sparse
                            processing_strategy = "fast_fallback"
                finally:
                    sys.stderr = old_stderr
            else:
                # Non-PDF: Standard partitioning with timeout
                try:
                    elements = _process_with_timeout(tmp_path, ext, language, timeout=300)
                except TimeoutError:
                    log(f"   ⚠️  Processing timeout after 300s")
                    raise  # Re-raise to mark as failed
            
            log(f"   ✅ Extracted {len(elements)} elements")
            
            # Generate artifacts - convert to proper JSON
            # Convert element dicts to JSON-serializable format (handle numpy types)
            import numpy as np
            
            def convert_numpy_types(obj):
                """Recursively convert numpy types to native Python types"""
                if isinstance(obj, dict):
                    return {k: convert_numpy_types(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_numpy_types(item) for item in obj]
                elif isinstance(obj, tuple):
                    return tuple(convert_numpy_types(item) for item in obj)
                elif isinstance(obj, (np.integer, np.floating)):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, (np.str_, np.bytes_)):
                    return str(obj)
                else:
                    return obj
            
            # Convert elements to proper JSON format
            elements_list = []
            for el in elements:
                el_dict = el.to_dict()
                el_dict = convert_numpy_types(el_dict)
                elements_list.append(json.dumps(el_dict, ensure_ascii=False))
            
            elements_jsonl = "\n".join(elements_list)
            # Safely convert elements to strings, handling None and objects without __str__
            text_content = "\n\n".join(
                str(el) if el is not None and hasattr(el, '__str__') else ""
                for el in elements
            )
            
            # Check if text is empty - FAIL the processing if no text extracted
            text_stripped = text_content.strip()
            if len(text_stripped) == 0:
                error_msg = "No text extracted from document (0 bytes) - file may be image-only with failed OCR, blank, or corrupted"
                log(f"   ❌ {error_msg}")
                
                # Mark as FAILED_PROCESS
                database.upsert_file(
                    sha256=sha256,
                    s3_key=s3_key,
                    status=FileStatus.FAILED_PROCESS,
                    extension=ext,
                    processed_text_size=0,
                    error_message=error_msg,
                    error_type="EmptyContentError"
                )
                
                return None  # Return None to indicate failure
            
            log(f"   ✅ Extracted {len(text_stripped)} bytes of text")
            
            # Extract metadata from elements for enriched meta.json
            doc_title = None
            doc_author = None
            page_count = 0
            
            try:
                for el in elements:
                    el_type = getattr(el, 'category', None)
                    if not el_type:
                        el_type = el.__class__.__name__
                    
                    # Try to find title (first Title element)
                    if not doc_title and el_type == 'Title':
                        el_text = str(el).strip() if el is not None and hasattr(el, '__str__') else ""
                        if el_text and len(el_text) > 3:
                            doc_title = el_text[:200]  # Limit length
                    
                    # Count pages (PageBreak elements)
                    if el_type == 'PageBreak':
                        page_count += 1
                    
                    # Try to find author in metadata (first element only, don't scan all)
                    if not doc_author and hasattr(el, 'metadata') and isinstance(el.metadata, dict):
                        for author_field in ['author', 'Author', 'creator', 'Creator']:
                            if author_field in el.metadata and el.metadata[author_field]:
                                doc_author = str(el.metadata[author_field])[:100]
                                break
                        if doc_author:
                            break  # Stop looking once we find an author
            except Exception as e:
                # Don't let metadata extraction break processing
                log(f"   ⚠️  Metadata extraction issue: {e}")
            
            # Build comprehensive meta.json
            processed_at = datetime.now()
            
            # Get synced_at timestamp from database if available
            # Convert datetime objects to ISO format strings for JSON serialization
            synced_at = None
            if file_record and file_record.get('created_at'):
                created = file_record['created_at']
                synced_at = created.isoformat() if hasattr(created, 'isoformat') else str(created)
            
            # Helper to convert datetime to string
            def datetime_to_str(dt):
                if dt is None:
                    return None
                return dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)
            
            meta_info = {
                # File identification
                "sha256": sha256,
                "original_filename": original_name,
                "s3_key": s3_key,
                "extension": ext,
                
                # Content metadata
                "element_count": len(elements),
                "text_length": len(text_content),
                "word_count": len(text_content.split()),
                "page_count": page_count if page_count > 0 else None,
                
                # Extracted document metadata
                "title": doc_title,
                "author": doc_author,
                
                # Processing metadata
                "language": language,
                "synced_at": synced_at,
                "processed_at": processed_at.isoformat(),
                "processing_strategy": processing_strategy,
                
                # Source metadata from S3 (Google Drive origin)
                "drive_file_id": file_record.get('drive_file_id') if file_record else None,
                "drive_path": file_record.get('drive_path') if file_record else None,
                "drive_created_time": datetime_to_str(file_record.get('drive_created_time')) if file_record else None,
                "drive_modified_time": datetime_to_str(file_record.get('drive_modified_time')) if file_record else None,
                "drive_mime_type": file_record.get('drive_mime_type') if file_record else None,
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
            
            # Mark as PROCESSED in database (clear any previous errors)
            database.upsert_file(
                sha256=sha256,
                s3_key=s3_key,
                status=FileStatus.PROCESSED,
                extension=ext,
                processed_text_size=len(text_content),
                error_message="",  # Empty string to clear error
                error_type=""
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


def _process_file_worker(sha256: str, s3_key: str, config: Config, db_config: dict, dry_run: bool, quiet_mode: bool) -> Optional[str]:
    """
    Standalone worker function for ProcessPoolExecutor.
    
    This function must be at module level (not a method) to be pickled.
    It initializes S3 and database clients and delegates to the shared processing logic.
    
    Args:
        sha256: SHA-256 hash of the file
        s3_key: S3 object key to process
        config: Configuration object
        db_config: Dictionary with PostgreSQL connection parameters
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
    
    database = Database(**db_config)
    
    # Delegate to shared processing logic
    return _process_single_file(sha256, s3_key, s3, database, dry_run, quiet_mode)


class UnstructuredProcessor:
    """
    Process documents using Unstructured.io
    
    Features:
    - Memory-efficient streaming downloads from S3
    - Fast text extraction with OCR fallback for PDFs
    - Timeout protection (300s = 5 minutes for all file types)
    - Parallel processing with ThreadPoolExecutor (default: 5 workers)
    - Automatic cleanup of temp files and hung processes
    """
    
    def __init__(self, config: Config, database: Database, dry_run: bool = False, max_workers: Optional[int] = None, use_processes: bool = False):
        self.config = config
        self.database = database
        self.dry_run = dry_run
        self.max_workers = max_workers or config.processor_max_workers
        self.use_processes = use_processes  # Use ProcessPoolExecutor for CPU-bound tasks
        self.quiet_mode = False  # Set to True to suppress per-file logging in parallel mode
        
        logger.info(f"🔧 Processor initialized: {self.max_workers} workers, timeout protection enabled")
        
        # Initialize S3 client with connection pooling
        self.s3 = S3Client(
            endpoint=config.s3_endpoint,
            access_key=config.s3_access_key,
            secret_key=config.s3_secret_key,
            bucket=config.s3_bucket,
            region=config.s3_region
        )
    
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
                # Get BOTH synced files AND failed files for retry
                synced_files = self.database.get_files_for_processing(limit=max_files)
                failed_files = self.database.get_files_by_status(FileStatus.FAILED_PROCESS, limit=max_files)
                
                # Combine and deduplicate by SHA256
                seen_sha256 = set()
                files = []
                for file in synced_files + failed_files:
                    if file["sha256"] not in seen_sha256:
                        files.append(file)
                        seen_sha256.add(file["sha256"])
                
                # Apply limit after combining
                if max_files and len(files) > max_files:
                    files = files[:max_files]
                
                logger.info(f"✅ Found {len(synced_files)} unprocessed files and {len(failed_files)} failed files to retry (total: {len(files)})")
            else:
                # Get files with SYNCED status only
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
        # Install global stderr filter to suppress deprecation warnings
        sys.stderr = DeprecationWarningFilter(sys.__stderr__)
        
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
                    # Pass database config as dict
                    db_config = {
                        "host": self.database.connection_params["host"],
                        "port": self.database.connection_params["port"],
                        "database": self.database.connection_params["database"],
                        "user": self.database.connection_params["user"],
                        "password": self.database.connection_params["password"]
                    }
                    future_to_key = {
                        executor.submit(_process_file_worker, sha256, s3_key, self.config, db_config, self.dry_run, self.quiet_mode): (s3_key, sha256)
                        for s3_key, sha256 in files
                    }
                else:
                    # For ThreadPoolExecutor, use the instance method
                    future_to_key = {
                        executor.submit(self.process_file, s3_key, sha256): (s3_key, sha256)
                        for s3_key, sha256 in files
                    }
                
                # Use tqdm for progress bar - write to stdout, suppress stderr completely
                import contextlib
                with open(os.devnull, 'w') as stderr_devnull:
                    with contextlib.redirect_stderr(stderr_devnull):
                        with tqdm(total=len(files), desc="🔄 Processing files", unit="file", 
                                  leave=True, dynamic_ncols=True, file=sys.stdout) as pbar:
                            for future in as_completed(future_to_key):
                                s3_key, sha256 = future_to_key[future]
                                try:
                                    result_sha256 = future.result()
                                    tracker.update(success=bool(result_sha256))
                                    if result_sha256:
                                        processed_sha256_hashes.append(result_sha256)
                                except Exception as e:
                                    tqdm.write(f"ERROR: {s3_key}: {e}")
                                    tracker.update(success=False)
                                
                                pbar.set_postfix_str(f"✅ {tracker.successful} | ❌ {tracker.failed}")
                                pbar.update(1)
            
            # Restore normal logging
            self.quiet_mode = False
        else:
            # Sequential processing
            import contextlib
            with open(os.devnull, 'w') as stderr_devnull:
                with contextlib.redirect_stderr(stderr_devnull):
                    with tqdm(total=len(files), desc="🔄 Processing files", unit="file",
                              leave=True, dynamic_ncols=True, file=sys.stdout) as pbar:
                        for s3_key, sha256 in files:
                            result_sha256 = self.process_file(s3_key, sha256)
                            tracker.update(success=bool(result_sha256))
                            
                            if result_sha256:
                                processed_sha256_hashes.append(result_sha256)
                            
                            pbar.set_postfix_str(f"✅ {tracker.successful} | ❌ {tracker.failed}")
                            pbar.update(1)
        
        # Ensure all logging handlers are flushed before attempting to log
        # This prevents "I/O operation on closed file" errors
        for handler in logger.handlers:
            try:
                handler.flush()
            except:
                pass
        
        # Summary
        print("\n" + "="*80)
        print(f"✅ Processing complete: {tracker.successful} successful, {tracker.failed} failed")
        print("="*80)
        
        return tracker.successful, tracker.failed, processed_sha256_hashes
    
    def process_batch_chunked(self, max_files: Optional[int] = None, chunk_size: int = 100, 
                             parallel: bool = True, retry_failed: bool = False, 
                             filter_sha256: Optional[List[str]] = None) -> Tuple[int, int, List[str]]:
        """
        Process files in chunks to avoid memory buildup (RECOMMENDED for large batches).
        
        This method processes files in manageable chunks with explicit garbage collection
        between chunks to prevent memory leaks and OOM errors.
        
        Args:
            max_files: Total maximum number of files to process (None = no limit)
            chunk_size: Files per chunk (default: 100, good for 8-16GB RAM)
            parallel: Use parallel processing (default: True)
            retry_failed: If True, retry previously failed files
            filter_sha256: Optional list of SHA256 hashes to process (for full pipeline)
        
        Returns:
            Tuple of (total_successful, total_failed, all_processed_sha256_hashes)
        """
        logger.info("="*80)
        logger.info("🔄 Starting Chunked Processing (Memory-Efficient)")
        if self.dry_run:
            logger.info("   [DRY RUN MODE - No changes will be made]")
        if parallel:
            executor_type = "ProcessPoolExecutor" if self.use_processes else "ThreadPoolExecutor"
            logger.info(f"   [PARALLEL MODE - {self.max_workers} workers using {executor_type}]")
        if retry_failed:
            logger.info("   [RETRY MODE - Including previously failed files]")
        if filter_sha256:
            logger.info(f"   [FILTERED MODE - Processing {len(filter_sha256)} specific files from sync stage]")
        logger.info(f"   [CHUNK SIZE - {chunk_size} files per chunk]")
        logger.info("="*80)
        
        # Get all files to process
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
        
        total_successful = 0
        total_failed = 0
        all_processed_sha256s = []
        
        # Process in chunks
        total_chunks = (len(files) + chunk_size - 1) // chunk_size
        
        for i in range(0, len(files), chunk_size):
            chunk = files[i:i + chunk_size]
            chunk_num = (i // chunk_size) + 1
            
            logger.info(f"\n{'='*80}")
            logger.info(f"📦 Processing Chunk {chunk_num}/{total_chunks} ({len(chunk)} files)")
            logger.info(f"{'='*80}")
            
            # Process this chunk
            success, failed, sha256s = self._process_chunk(chunk, parallel)
            
            total_successful += success
            total_failed += failed
            all_processed_sha256s.extend(sha256s)
            
            # Explicit cleanup between chunks
            gc.collect()
            
            logger.info(f"✅ Chunk {chunk_num} complete: {success} success, {failed} failed")
            if len(files) > 0:
                progress_pct = 100.0 * (i + len(chunk)) / len(files)
                logger.info(f"📊 Overall progress: {total_successful + total_failed}/{len(files)} ({progress_pct:.1f}%)")
        
        # Final summary
        print("\n" + "="*80)
        print(f"✅ Chunked processing complete: {total_successful} successful, {total_failed} failed")
        print("="*80)
        
        return total_successful, total_failed, all_processed_sha256s
    
    def _process_chunk(self, files: List[Tuple[str, str]], parallel: bool) -> Tuple[int, int, List[str]]:
        """
        Process a single chunk of files.
        
        Args:
            files: List of (s3_key, sha256) tuples
            parallel: Use parallel processing
        
        Returns:
            Tuple of (successful_count, failed_count, processed_sha256_hashes)
        """
        tracker = ProgressTracker(len(files), "Processing")
        processed_sha256_hashes = []
        
        if parallel and self.max_workers > 1:
            ExecutorClass = ProcessPoolExecutor if self.use_processes else ThreadPoolExecutor
            self.quiet_mode = True
            
            with ExecutorClass(max_workers=self.max_workers) as executor:
                if self.use_processes:
                    db_config = {
                        "host": self.database.connection_params["host"],
                        "port": self.database.connection_params["port"],
                        "database": self.database.connection_params["database"],
                        "user": self.database.connection_params["user"],
                        "password": self.database.connection_params["password"]
                    }
                    future_to_key = {
                        executor.submit(_process_file_worker, sha256, s3_key, self.config, db_config, self.dry_run, self.quiet_mode): (s3_key, sha256)
                        for s3_key, sha256 in files
                    }
                else:
                    future_to_key = {
                        executor.submit(self.process_file, s3_key, sha256): (s3_key, sha256)
                        for s3_key, sha256 in files
                    }
                
                with tqdm(total=len(files), desc="🔄 Processing chunk", unit="file", 
                          leave=False, dynamic_ncols=True) as pbar:
                    for future in as_completed(future_to_key):
                        s3_key, sha256 = future_to_key[future]
                        try:
                            result_sha256 = future.result()
                            tracker.update(success=bool(result_sha256))
                            if result_sha256:
                                processed_sha256_hashes.append(result_sha256)
                        except Exception as e:
                            tracker.update(success=False)
                        
                        pbar.set_postfix_str(f"✅ {tracker.successful} | ❌ {tracker.failed}")
                        pbar.update(1)
            
            self.quiet_mode = False
        else:
            # Sequential processing
            with tqdm(total=len(files), desc="🔄 Processing chunk", unit="file", leave=False) as pbar:
                for s3_key, sha256 in files:
                    result_sha256 = self.process_file(s3_key, sha256)
                    tracker.update(success=bool(result_sha256))
                    if result_sha256:
                        processed_sha256_hashes.append(result_sha256)
                    pbar.set_postfix_str(f"✅ {tracker.successful} | ❌ {tracker.failed}")
                    pbar.update(1)
        
        return tracker.successful, tracker.failed, processed_sha256_hashes
