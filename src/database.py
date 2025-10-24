"""SQLite database for pipeline state management"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from enum import Enum

from .utils import setup_logging

logger = setup_logging(__name__)


class FileStatus(Enum):
    """File processing status states"""
    SYNCED = "synced"              # Downloaded from Drive to S3 objects/
    PROCESSING = "processing"       # Being processed by Unstructured
    PROCESSED = "processed"         # Processing complete, derivatives/ created
    INDEXING = "indexing"          # Being indexed to Vector Store
    INDEXED = "indexed"            # Successfully indexed to Vector Store
    FAILED_SYNC = "failed_sync"    # Failed during sync
    FAILED_PROCESS = "failed_process"  # Failed during processing
    FAILED_INDEX = "failed_index"   # Failed during indexing


class Database:
    """SQLite database for pipeline state management"""
    
    def __init__(self, db_path: str = "pipeline.db"):
        """
        Initialize database connection
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_schema()
        self._enable_wal_mode()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections with proper timeout and isolation"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,  # Wait up to 30 seconds for locks
            isolation_level='DEFERRED'  # Better concurrency for read-heavy workloads
        )
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_schema(self):
        """Initialize database schema with proper indexing"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Main file state table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_state (
                    sha256 TEXT PRIMARY KEY,
                    drive_file_id TEXT,
                    drive_path TEXT,
                    original_name TEXT,
                    s3_key TEXT NOT NULL,
                    extension TEXT,
                    status TEXT NOT NULL,
                    
                    -- Stage timestamps
                    synced_at TEXT,
                    processed_at TEXT,
                    indexed_at TEXT,
                    
                    -- OpenAI references
                    openai_file_id TEXT,
                    vector_store_id TEXT,
                    
                    -- Error tracking
                    error_message TEXT,
                    error_type TEXT,
                    retry_count INTEGER DEFAULT 0,
                    last_error_at TEXT,
                    
                    -- Metadata
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Create indexes for common queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_status 
                ON file_state(status)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_drive_file_id 
                ON file_state(drive_file_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_updated_at 
                ON file_state(updated_at)
            """)
            
            # Checkpoint table for incremental sync
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS checkpoint (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            logger.debug(f"✅ Database schema initialized: {self.db_path}")
    
    def _enable_wal_mode(self):
        """
        Enable Write-Ahead Logging (WAL) mode for better concurrency.
        
        WAL mode allows multiple readers and one writer to operate concurrently,
        dramatically improving performance when using ProcessPoolExecutor.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")  # Faster writes, still safe
            cursor.execute("PRAGMA busy_timeout=30000")  # 30 second timeout
            logger.debug("✅ WAL mode enabled for better concurrency")
    
    # ==================== FILE STATE MANAGEMENT ====================
    
    def upsert_file(self, sha256: str, s3_key: str, status: FileStatus,
                   drive_file_id: Optional[str] = None,
                   drive_path: Optional[str] = None,
                   original_name: Optional[str] = None,
                   extension: Optional[str] = None,
                   openai_file_id: Optional[str] = None,
                   vector_store_id: Optional[str] = None,
                   error_message: Optional[str] = None,
                   error_type: Optional[str] = None) -> None:
        """
        Insert or update file state
        
        Args:
            sha256: File SHA-256 hash (primary key)
            s3_key: S3 object key
            status: Current processing status
            drive_file_id: Google Drive file ID
            drive_path: Path in Google Drive
            original_name: Original filename
            extension: File extension
            openai_file_id: OpenAI file ID (if indexed)
            vector_store_id: Vector Store ID (if indexed)
            error_message: Error message (if failed)
            error_type: Error type (if failed)
        """
        now = datetime.utcnow().isoformat()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if file exists
            cursor.execute("SELECT * FROM file_state WHERE sha256 = ?", (sha256,))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing record
                updates = {
                    "status": status.value,
                    "updated_at": now,
                    "s3_key": s3_key
                }
                
                # Update optional fields if provided
                if drive_file_id is not None:
                    updates["drive_file_id"] = drive_file_id
                if drive_path is not None:
                    updates["drive_path"] = drive_path
                if original_name is not None:
                    updates["original_name"] = original_name
                if extension is not None:
                    updates["extension"] = extension
                if openai_file_id is not None:
                    updates["openai_file_id"] = openai_file_id
                if vector_store_id is not None:
                    updates["vector_store_id"] = vector_store_id
                
                # Handle error tracking
                if error_message is not None:
                    updates["error_message"] = error_message
                    updates["error_type"] = error_type
                    updates["last_error_at"] = now
                    updates["retry_count"] = existing["retry_count"] + 1
                
                # Update stage timestamps based on status
                if status == FileStatus.SYNCED and not existing["synced_at"]:
                    updates["synced_at"] = now
                elif status == FileStatus.PROCESSED and not existing["processed_at"]:
                    updates["processed_at"] = now
                elif status == FileStatus.INDEXED and not existing["indexed_at"]:
                    updates["indexed_at"] = now
                
                # Build UPDATE query
                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                values = list(updates.values()) + [sha256]
                
                cursor.execute(f"""
                    UPDATE file_state 
                    SET {set_clause}
                    WHERE sha256 = ?
                """, values)
            else:
                # Insert new record
                cursor.execute("""
                    INSERT INTO file_state (
                        sha256, drive_file_id, drive_path, original_name, 
                        s3_key, extension, status,
                        synced_at, openai_file_id, vector_store_id,
                        error_message, error_type, retry_count, last_error_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sha256, drive_file_id, drive_path, original_name,
                    s3_key, extension, status.value,
                    now if status == FileStatus.SYNCED else None,
                    openai_file_id, vector_store_id,
                    error_message, error_type, 0, 
                    now if error_message else None,
                    now, now
                ))
    
    def get_file_by_sha256(self, sha256: str) -> Optional[Dict]:
        """Get file state by SHA-256"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM file_state WHERE sha256 = ?", (sha256,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_file_by_drive_id(self, drive_file_id: str) -> Optional[Dict]:
        """Get file state by Google Drive file ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM file_state WHERE drive_file_id = ?", 
                (drive_file_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_files_by_status(self, status: FileStatus, limit: Optional[int] = None) -> List[Dict]:
        """Get all files with a specific status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM file_state WHERE status = ? ORDER BY updated_at DESC"
            if limit:
                query += f" LIMIT {limit}"
            cursor.execute(query, (status.value,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_files_for_processing(self, limit: Optional[int] = None) -> List[Dict]:
        """Get files ready for processing (status=SYNCED)"""
        return self.get_files_by_status(FileStatus.SYNCED, limit)
    
    def get_files_for_indexing(self, limit: Optional[int] = None) -> List[Dict]:
        """Get files ready for indexing (status=PROCESSED)"""
        return self.get_files_by_status(FileStatus.PROCESSED, limit)
    
    def get_stale_processing_files(self, max_age_hours: int = 24) -> List[Dict]:
        """
        Get files stuck in PROCESSING or INDEXING state for too long
        
        Args:
            max_age_hours: Maximum age in hours before considering stale
        
        Returns:
            List of stale file records
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM file_state 
                WHERE status IN ('processing', 'indexing')
                AND datetime(updated_at) < datetime('now', '-' || ? || ' hours')
                ORDER BY updated_at ASC
            """, (max_age_hours,))
            return [dict(row) for row in cursor.fetchall()]
    
    def mark_stale_as_failed(self, max_age_hours: int = 24) -> int:
        """
        Mark stale PROCESSING/INDEXING files as FAILED
        
        Returns:
            Number of files marked as failed
        """
        stale_files = self.get_stale_processing_files(max_age_hours)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            
            for file in stale_files:
                if file["status"] == "processing":
                    new_status = FileStatus.FAILED_PROCESS.value
                else:
                    new_status = FileStatus.FAILED_INDEX.value
                
                cursor.execute("""
                    UPDATE file_state 
                    SET status = ?, 
                        error_message = ?,
                        error_type = 'StaleProcessing',
                        last_error_at = ?,
                        updated_at = ?
                    WHERE sha256 = ?
                """, (
                    new_status,
                    f"File stuck in {file['status']} for more than {max_age_hours} hours",
                    now, now, file["sha256"]
                ))
        
        return len(stale_files)
    
    # ==================== CHECKPOINT MANAGEMENT ====================
    
    def get_checkpoint(self, key: str) -> Optional[str]:
        """Get checkpoint value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM checkpoint WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else None
    
    def set_checkpoint(self, key: str, value: str) -> None:
        """Set checkpoint value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute("""
                INSERT OR REPLACE INTO checkpoint (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, value, now))
    
    # ==================== STATISTICS ====================
    
    def get_statistics(self) -> Dict[str, int]:
        """Get pipeline statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Count by status
            for status in FileStatus:
                cursor.execute(
                    "SELECT COUNT(*) as count FROM file_state WHERE status = ?",
                    (status.value,)
                )
                stats[status.value] = cursor.fetchone()["count"]
            
            # Total files
            cursor.execute("SELECT COUNT(*) as count FROM file_state")
            stats["total"] = cursor.fetchone()["count"]
            
            # Files with errors
            cursor.execute("""
                SELECT COUNT(*) as count FROM file_state 
                WHERE error_message IS NOT NULL
            """)
            stats["with_errors"] = cursor.fetchone()["count"]
            
            return stats
    
    # ==================== MIGRATION FROM S3 MARKERS ====================
    
    def migrate_from_s3_markers(self, s3_client, bucket: str, dry_run: bool = False) -> Tuple[int, int, int]:
        """
        Migrate existing S3 markers to database
        
        Scans objects/, derivatives/, indexed/, and failed/ prefixes to build
        the initial database state.
        
        Args:
            s3_client: S3Client instance
            bucket: S3 bucket name
            dry_run: If True, only report what would be migrated
        
        Returns:
            Tuple of (synced_count, processed_count, indexed_count)
        """
        logger.info("🔄 Migrating existing S3 state to database...")
        
        synced_count = 0
        processed_count = 0
        indexed_count = 0
        
        # Step 1: Scan objects/ for synced files
        logger.info("   📊 Scanning objects/...")
        for key in s3_client.list_objects("objects/"):
            if key.endswith("/"):
                continue
            
            # Extract SHA-256: objects/aa/bb/sha256.ext
            sha256 = Path(key).stem
            extension = Path(key).suffix
            
            # Get metadata
            try:
                _, metadata = s3_client.get_object_metadata(key)
                drive_file_id = metadata.get("drive-file-id")
                original_name = metadata.get("original-name")
                drive_path = metadata.get("drive-path")
            except Exception:
                drive_file_id = None
                original_name = None
                drive_path = None
            
            if not dry_run:
                # Check if already processed or indexed
                existing = self.get_file_by_sha256(sha256)
                if not existing:
                    self.upsert_file(
                        sha256=sha256,
                        s3_key=key,
                        status=FileStatus.SYNCED,
                        drive_file_id=drive_file_id,
                        original_name=original_name,
                        drive_path=drive_path,
                        extension=extension
                    )
                    synced_count += 1
        
        # Step 2: Scan derivatives/ for processed files
        logger.info("   📊 Scanning derivatives/...")
        for key in s3_client.list_objects("derivatives/"):
            if not key.endswith("/meta.json"):
                continue
            
            # Extract SHA-256: derivatives/aa/bb/sha256/meta.json
            parts = key.split("/")
            if len(parts) >= 4:
                sha256 = parts[3]
                
                if not dry_run:
                    # Update status to PROCESSED
                    existing = self.get_file_by_sha256(sha256)
                    if existing:
                        # Load metadata for extension
                        try:
                            meta_data, _ = s3_client.get_object(key)
                            metadata = json.loads(meta_data.decode("utf-8"))
                            extension = metadata.get("extension", "")
                            
                            self.upsert_file(
                                sha256=sha256,
                                s3_key=existing["s3_key"],
                                status=FileStatus.PROCESSED,
                                extension=extension
                            )
                            processed_count += 1
                        except Exception as e:
                            logger.warning(f"   Could not load metadata for {sha256}: {e}")
        
        # Step 3: Scan indexed/ for indexed files
        logger.info("   📊 Scanning indexed/...")
        for key in s3_client.list_objects("indexed/"):
            if key.endswith(".indexed"):
                # Extract SHA-256: indexed/aa/sha256.indexed
                parts = key.split("/")
                if len(parts) >= 3:
                    sha256 = Path(parts[-1]).stem
                    
                    if not dry_run:
                        # Load marker to get OpenAI file ID
                        try:
                            marker_data, _ = s3_client.get_object(key)
                            marker = json.loads(marker_data.decode("utf-8"))
                            openai_file_id = marker.get("openai_file_id")
                            vector_store_id = marker.get("vector_store_id")
                            
                            existing = self.get_file_by_sha256(sha256)
                            if existing:
                                self.upsert_file(
                                    sha256=sha256,
                                    s3_key=existing["s3_key"],
                                    status=FileStatus.INDEXED,
                                    openai_file_id=openai_file_id,
                                    vector_store_id=vector_store_id
                                )
                                indexed_count += 1
                        except Exception as e:
                            logger.warning(f"   Could not load indexed marker for {sha256}: {e}")
        
        # Step 4: Scan failed/ for failed files
        logger.info("   📊 Scanning failed/...")
        for key in s3_client.list_objects("failed/"):
            if key.endswith(".txt"):
                # Extract SHA-256: failed/aa/sha256.txt
                parts = key.split("/")
                if len(parts) >= 3:
                    sha256 = Path(parts[-1]).stem
                    
                    if not dry_run:
                        # Load error info
                        try:
                            error_data, _ = s3_client.get_object(key)
                            error_info = json.loads(error_data.decode("utf-8"))
                            
                            existing = self.get_file_by_sha256(sha256)
                            if existing:
                                self.upsert_file(
                                    sha256=sha256,
                                    s3_key=existing["s3_key"],
                                    status=FileStatus.FAILED_PROCESS,
                                    error_message=error_info.get("error"),
                                    error_type=error_info.get("error_type")
                                )
                        except Exception as e:
                            logger.warning(f"   Could not load error info for {sha256}: {e}")
        
        logger.info(f"   ✅ Migration complete: {synced_count} synced, {processed_count} processed, {indexed_count} indexed")
        
        return synced_count, processed_count, indexed_count
