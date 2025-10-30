"""Docling processing engine - IBM's advanced document parsing library
 
Docling features:
- Advanced PDF understanding with layout analysis
- Built-in OCR support (Auto, Tesseract, RapidOCR, EasyOCR, OcrMac)
- Better handling of complex documents (tables, images, equations)
- Support for multiple formats: PDF, DOCX, PPTX, images
- Clean markdown export
- Faster than Unstructured for many document types
 
Installation: pip install "docling>=2.0.0"
"""

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import Config
from .database import Database, FileStatus
from .utils import S3Client, setup_logging

logger = setup_logging(__name__)


def _process_with_docling(tmp_path: str, ext: str, language: str = "eng") -> Tuple[str, str, Dict]:
    """
    Process document using Docling library
    
    Args:
        tmp_path: Path to temporary file
        ext: File extension (e.g., '.pdf', '.docx')
        language: Language hint for OCR (e.g., 'eng', 'hun')
    
    Returns:
        Tuple of (text_content, elements_jsonl, metadata)
    """
    try:
        from docling.document_converter import DocumentConverter
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            TesseractOcrOptions,
        )
    except ImportError:
        raise ImportError(
            "Docling is not installed. Install with: pip install docling\n"
            "Or enable it in the Dockerfile by uncommenting the docling installation line."
        )
    
    # Configure pipeline based on file type
    if ext == '.pdf':
        # PDF with OCR support
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True  # Enable OCR for scanned PDFs
        pipeline_options.do_table_structure = True  # Enable table recognition
        
        # Configure Tesseract OCR with language support
        # Map language codes to Tesseract format
        lang_map = {
            'eng': ['eng'],
            'hun': ['hun'],
            'eng+hun': ['eng', 'hun'],
            'ces': ['ces'],
            'slk': ['slk'],
            'pol': ['pol'],
            'deu': ['deu'],
            'fra': ['fra'],
            'spa': ['spa'],
            'ita': ['ita'],
            'ron': ['ron'],
        }
        
        tesseract_langs = lang_map.get(language, ['eng', 'hun'])
        pipeline_options.ocr_options = TesseractOcrOptions(
            lang=tesseract_langs,
            force_full_page_ocr=False,  # Only OCR if needed
        )
        
        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            pipeline_options=pipeline_options,
        )
    else:
        # Other formats (DOCX, PPTX, images, etc.)
        converter = DocumentConverter()
    
    # Convert document
    result = converter.convert(tmp_path)
    doc = result.document
    
    # Extract text content as markdown
    text_content = doc.export_to_markdown()
    
    # Extract structured elements as JSON
    # Docling provides hierarchical document structure
    elements = []
    for item, level in doc.iterate_items():
        element_dict = {
            "type": item.__class__.__name__,
            "level": level,
            "text": item.text if hasattr(item, 'text') else str(item),
        }
        
        # Add additional properties if available
        if hasattr(item, 'label'):
            element_dict["label"] = item.label
        if hasattr(item, 'prov'):
            element_dict["prov"] = str(item.prov)
            
        elements.append(element_dict)
    
    # Convert elements to JSONL format
    elements_jsonl = "\n".join(json.dumps(el, ensure_ascii=False) for el in elements)
    
    # Build metadata
    metadata = {
        "processing_engine": "docling",
        "num_elements": len(elements),
        "num_chars": len(text_content),
        "docling_version": result.status.value if hasattr(result, 'status') else "unknown",
    }
    
    # Add page count if available
    if hasattr(doc, 'pages') and doc.pages:
        metadata["num_pages"] = len(doc.pages)
    
    logger.info(f"   ✅ Docling extracted {len(elements)} elements, {len(text_content)} chars")
    
    return text_content, elements_jsonl, metadata


class DoclingProcessor:
    """
    Process documents using IBM's Docling library
    
    Features:
    - Advanced PDF understanding with layout analysis
    - Multiple OCR engine support (Tesseract, RapidOCR, EasyOCR)
    - Better table and equation recognition
    - Faster processing for complex documents
    - Clean markdown export
    """
    
    def __init__(self, config: Config, database: Database, dry_run: bool = False):
        self.config = config
        self.database = database
        self.dry_run = dry_run
        
        logger.info(f"🔧 Docling Processor initialized")
        
        # Initialize S3 client
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
    
    def process_single_file(self, s3_key: str, sha256: str) -> bool:
        """
        Process a single file using Docling
        
        Args:
            s3_key: S3 key of the file
            sha256: SHA-256 hash of the file
        
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"📄 Processing: {s3_key}")
        
        try:
            # Download file from S3
            ext = Path(s3_key).suffix.lower()
            tmp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
            tmp_path = tmp_file.name
            
            stream, metadata = self.s3.get_object_stream(s3_key)
            for chunk in stream.iter_chunks(chunk_size=8192):
                tmp_file.write(chunk)
            tmp_file.close()
            
            # Detect language from filename (reuse logic from unstructured processor)
            language = self._get_language_hint(s3_key)
            
            # Process with Docling
            try:
                text_content, elements_jsonl, doc_metadata = _process_with_docling(
                    tmp_path, ext, language
                )
                
                # Check if text is empty
                if len(text_content.strip()) == 0:
                    error_msg = "No text extracted from document (0 bytes)"
                    logger.warning(f"   ⚠️  {error_msg}")
                    if not self.dry_run:
                        self.database.mark_file_failed(sha256, error_msg)
                    os.unlink(tmp_path)
                    return False
                
                # Upload artifacts to S3
                if not self.dry_run:
                    # Upload JSONL elements
                    jsonl_key = f"{s3_key}.elements.jsonl"
                    self.s3.upload_content(elements_jsonl.encode('utf-8'), jsonl_key)
                    
                    # Upload text content
                    text_key = f"{s3_key}.txt"
                    self.s3.upload_content(text_content.encode('utf-8'), text_key)
                    
                    # Update database with metadata including Docling info
                    file_size = metadata.get('ContentLength', 0)
                    self.database.mark_file_processed(
                        sha256=sha256,
                        text_key=text_key,
                        jsonl_key=jsonl_key,
                        text_size=len(text_content),
                        file_size=file_size,
                        metadata=doc_metadata,
                    )
                
                logger.info(f"   ✅ Processed successfully with Docling")
                os.unlink(tmp_path)
                return True
                
            except Exception as e:
                error_msg = f"Docling processing error: {str(e)}"
                logger.error(f"   ❌ {error_msg}")
                if not self.dry_run:
                    self.database.mark_file_failed(sha256, error_msg)
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                return False
                
        except Exception as e:
            error_msg = f"Error processing file: {str(e)}"
            logger.error(f"   ❌ {error_msg}")
            if not self.dry_run:
                self.database.mark_file_failed(sha256, error_msg)
            return False
    
    def list_incoming_files(self, max_files: Optional[int] = None, retry_failed: bool = False) -> List[Tuple[str, str]]:
        """List files ready for processing"""
        logger.info(f"🔍 Querying database for files ready to process...")
        
        try:
            if retry_failed:
                synced_files = self.database.get_files_for_processing(limit=max_files)
                failed_files = self.database.get_files_by_status(FileStatus.FAILED_PROCESS, limit=max_files)
                
                seen_sha256 = set()
                files = []
                for file in synced_files + failed_files:
                    if file["sha256"] not in seen_sha256:
                        files.append(file)
                        seen_sha256.add(file["sha256"])
                
                if max_files and len(files) > max_files:
                    files = files[:max_files]
                
                logger.info(f"✅ Found {len(synced_files)} unprocessed + {len(failed_files)} failed (total: {len(files)})")
            else:
                files = self.database.get_files_for_processing(limit=max_files)
                logger.info(f"✅ Found {len(files)} unprocessed files")
            
            return [(file["s3_key"], file["sha256"]) for file in files]
        
        except Exception as e:
            logger.error(f"Error querying database: {e}")
            return []
    
    def process_batch(self, max_files: Optional[int] = None, parallel: bool = True, 
                     retry_failed: bool = False, filter_sha256: Optional[List[str]] = None) -> Tuple[int, int, List[str]]:
        """
        Process a batch of files with Docling
        
        Args:
            max_files: Maximum number of files to process
            parallel: Ignored (Docling processes sequentially for now)
            retry_failed: If True, retry previously failed files
            filter_sha256: Optional list of SHA256 hashes to process
        
        Returns:
            Tuple of (successful_count, failed_count, list_of_processed_sha256_hashes)
        """
        logger.info("="*80)
        logger.info("� Starting Docling Processing (IBM Research Document Converter)")
        if self.dry_run:
            logger.info("   [DRY RUN MODE - No changes will be made]")
        if retry_failed:
            logger.info("   [RETRY MODE - Including previously failed files]")
        if filter_sha256:
            logger.info(f"   [FILTERED MODE - Processing {len(filter_sha256)} specific files]")
        logger.info("="*80)
        
        # List incoming files
        files = self.list_incoming_files(max_files=max_files, retry_failed=retry_failed)
        
        # Filter by SHA256 if specified
        if filter_sha256:
            filter_set = set(filter_sha256)
            files = [(s3_key, sha256) for s3_key, sha256 in files if sha256 in filter_set]
            logger.info(f"   Filtered to {len(files)} files from sync stage")
        
        if not files:
            logger.info("✨ No files to process")
            return 0, 0, []
        
        logger.info(f"🔍 Processing {len(files)} files with Docling...")
        
        # Process files sequentially
        success_count = 0
        failed_count = 0
        processed_hashes = []
        
        from tqdm import tqdm
        for s3_key, sha256 in tqdm(files, desc="Processing files"):
            if self.process_single_file(s3_key, sha256):
                success_count += 1
                processed_hashes.append(sha256)
            else:
                failed_count += 1
        
        logger.info(f"\n✅ Processing complete: {success_count} successful, ❌ {failed_count} failed")
        logger.info("="*80 + "\n")
        
        return success_count, failed_count, processed_hashes
    
    def _get_language_hint(self, s3_key: str) -> str:
        """Detect language hint from filename (same as unstructured processor)"""
        import re
        
        s3_key_lower = s3_key.lower()
        lang_map = {
            'hun': 'hun', 'magyar': 'hun',
            'eng': 'eng', 'english': 'eng',
            'ces': 'ces', 'czech': 'ces',
            'slk': 'slk', 'slovak': 'slk',
            'pol': 'pol', 'polish': 'pol',
            'deu': 'deu', 'german': 'deu',
            'fra': 'fra', 'french': 'fra',
            'spa': 'spa', 'spanish': 'spa',
            'ita': 'ita', 'italian': 'ita',
            'ron': 'ron', 'romanian': 'ron',
        }
        
        pattern = r'[_\-](' + '|'.join(lang_map.keys()) + r')[_\-\.]'
        match = re.search(pattern, s3_key_lower)
        
        if match:
            return lang_map[match.group(1)]
        
        return "eng+hun"  # Default to English+Hungarian
