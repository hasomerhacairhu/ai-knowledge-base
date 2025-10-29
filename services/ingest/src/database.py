"""PostgreSQL database for pipeline state management"""

import json
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from datetime import datetime
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
    """PostgreSQL database for pipeline state management"""
    
    def __init__(self, host: str = "localhost", port: int = 5432, 
                 database: str = "ai_knowledge_base", user: str = "postgres", 
                 password: str = "postgres"):
        """
        Initialize database connection
        
        Args:
            host: PostgreSQL host
            port: PostgreSQL port
            database: Database name
            user: Database user
            password: Database password
        """
        self.connection_params = {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password,
            "connect_timeout": 10
        }
        self._init_schema()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = psycopg2.connect(**self.connection_params)
        conn.autocommit = False
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
                    synced_at TIMESTAMP,
                    processed_at TIMESTAMP,
                    indexed_at TIMESTAMP,
                    
                    -- Drive metadata
                    drive_created_time TIMESTAMP,
                    drive_modified_time TIMESTAMP,
                    drive_mime_type TEXT,
                    
                    -- File sizes
                    original_file_size BIGINT,
                    processed_text_size BIGINT,
                    
                    -- OpenAI references
                    openai_file_id TEXT,
                    vector_store_id TEXT,
                    
                    -- Error tracking
                    error_message TEXT,
                    error_type TEXT,
                    retry_count INTEGER DEFAULT 0,
                    last_error_at TIMESTAMP,
                    
                    -- Metadata
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
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
            
            # Drive file mapping table - tracks all Drive files pointing to same SHA256
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS drive_file_mapping (
                    drive_file_id TEXT PRIMARY KEY,
                    sha256 TEXT NOT NULL,
                    drive_path TEXT,
                    original_name TEXT,
                    drive_created_time TIMESTAMP,
                    drive_modified_time TIMESTAMP,
                    drive_mime_type TEXT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (sha256) REFERENCES file_state(sha256)
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_drive_mapping_sha256
                ON drive_file_mapping(sha256)
            """)
            
            # Checkpoint table for incremental sync
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS checkpoint (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
            """)
            
            logger.debug(f"✅ Database schema initialized: {self.connection_params['database']}")
    
    # ==================== FILE STATE MANAGEMENT ====================
    
    def upsert_file(self, sha256: str, s3_key: str, status: FileStatus,
                   drive_file_id: Optional[str] = None,
                   drive_path: Optional[str] = None,
                   original_name: Optional[str] = None,
                   extension: Optional[str] = None,
                   drive_created_time: Optional[str] = None,
                   drive_modified_time: Optional[str] = None,
                   drive_mime_type: Optional[str] = None,
                   original_file_size: Optional[int] = None,
                   processed_text_size: Optional[int] = None,
                   openai_file_id: Optional[str] = None,
                   vector_store_id: Optional[str] = None,
                   error_message: Optional[str] = None,
                   error_type: Optional[str] = None) -> bool:
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
            drive_created_time: Creation time in Drive (ISO format)
            drive_modified_time: Last modified time in Drive (ISO format)
            drive_mime_type: MIME type from Drive
            original_file_size: Size of original file in bytes
            processed_text_size: Size of processed text in bytes
            openai_file_id: OpenAI file ID (if indexed)
            vector_store_id: Vector Store ID (if indexed)
            error_message: Error message (if failed)
            error_type: Error type (if failed)
            
        Returns:
            bool: True if a new row was inserted, False if existing row was updated
        """
        now = datetime.utcnow()
        
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Check if file exists
            cursor.execute("SELECT * FROM file_state WHERE sha256 = %s", (sha256,))
            existing = cursor.fetchone()
            
            if existing:
                # Build dynamic UPDATE query based on provided values
                updates = ["status = %s", "updated_at = %s", "s3_key = %s"]
                values = [status.value, now, s3_key]
                
                # Update optional fields if provided
                if drive_file_id is not None:
                    updates.append("drive_file_id = %s")
                    values.append(drive_file_id)
                if drive_path is not None:
                    updates.append("drive_path = %s")
                    values.append(drive_path)
                if original_name is not None:
                    updates.append("original_name = %s")
                    values.append(original_name)
                if extension is not None:
                    updates.append("extension = %s")
                    values.append(extension)
                if drive_created_time is not None:
                    updates.append("drive_created_time = %s")
                    values.append(drive_created_time)
                if drive_modified_time is not None:
                    updates.append("drive_modified_time = %s")
                    values.append(drive_modified_time)
                if drive_mime_type is not None:
                    updates.append("drive_mime_type = %s")
                    values.append(drive_mime_type)
                if original_file_size is not None:
                    updates.append("original_file_size = %s")
                    values.append(original_file_size)
                if processed_text_size is not None:
                    updates.append("processed_text_size = %s")
                    values.append(processed_text_size)
                if openai_file_id is not None:
                    updates.append("openai_file_id = %s")
                    values.append(openai_file_id)
                if vector_store_id is not None:
                    updates.append("vector_store_id = %s")
                    values.append(vector_store_id)
                
                # Handle error tracking
                if error_message is not None:
                    updates.extend(["error_message = %s", "error_type = %s", 
                                  "last_error_at = %s", "retry_count = retry_count + 1"])
                    values.extend([error_message, error_type, now])
                
                # Update stage timestamps based on status
                if status == FileStatus.SYNCED and not existing["synced_at"]:
                    updates.append("synced_at = %s")
                    values.append(now)
                elif status == FileStatus.PROCESSED and not existing["processed_at"]:
                    updates.append("processed_at = %s")
                    values.append(now)
                elif status == FileStatus.INDEXED and not existing["indexed_at"]:
                    updates.append("indexed_at = %s")
                    values.append(now)
                
                # Add WHERE clause parameter
                values.append(sha256)
                
                # Execute UPDATE
                set_clause = ", ".join(updates)
                cursor.execute(f"""
                    UPDATE file_state 
                    SET {set_clause}
                    WHERE sha256 = %s
                """, values)
                
                return False  # Existing row was updated
            else:
                # Insert new record
                cursor.execute("""
                    INSERT INTO file_state (
                        sha256, drive_file_id, drive_path, original_name, 
                        s3_key, extension, status,
                        synced_at, drive_created_time, drive_modified_time, drive_mime_type,
                        original_file_size, processed_text_size,
                        openai_file_id, vector_store_id,
                        error_message, error_type, retry_count, last_error_at,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    sha256, drive_file_id, drive_path, original_name,
                    s3_key, extension, status.value,
                    now if status == FileStatus.SYNCED else None,
                    drive_created_time, drive_modified_time, drive_mime_type,
                    original_file_size, processed_text_size,
                    openai_file_id, vector_store_id,
                    error_message, error_type, 0, 
                    now if error_message else None,
                    now, now
                ))
                
                return True  # New row was inserted
    
    def upsert_drive_mapping(self, drive_file_id: str, sha256: str,
                            drive_path: Optional[str] = None,
                            original_name: Optional[str] = None,
                            drive_created_time: Optional[str] = None,
                            drive_modified_time: Optional[str] = None,
                            drive_mime_type: Optional[str] = None) -> None:
        """
        Track mapping between Drive file ID and content SHA256.
        This allows multiple Drive files to point to the same content.
        
        Args:
            drive_file_id: Google Drive file ID (primary key)
            sha256: Content SHA-256 hash
            drive_path: Path in Google Drive
            original_name: Original filename
            drive_created_time: Creation time in Drive
            drive_modified_time: Last modified time in Drive
            drive_mime_type: MIME type from Drive
        """
        now = datetime.utcnow()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Upsert the mapping using ON CONFLICT
            cursor.execute("""
                INSERT INTO drive_file_mapping (
                    drive_file_id, sha256, drive_path, original_name,
                    drive_created_time, drive_modified_time, drive_mime_type,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(drive_file_id) DO UPDATE SET
                    sha256 = EXCLUDED.sha256,
                    drive_path = EXCLUDED.drive_path,
                    original_name = EXCLUDED.original_name,
                    drive_created_time = EXCLUDED.drive_created_time,
                    drive_modified_time = EXCLUDED.drive_modified_time,
                    drive_mime_type = EXCLUDED.drive_mime_type,
                    updated_at = EXCLUDED.updated_at
            """, (drive_file_id, sha256, drive_path, original_name,
                  drive_created_time, drive_modified_time, drive_mime_type,
                  now, now))
    
    def get_drive_mapping(self, drive_file_id: str) -> Optional[Dict]:
        """Get Drive file mapping by Drive file ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("SELECT * FROM drive_file_mapping WHERE drive_file_id = %s", (drive_file_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_file_by_sha256(self, sha256: str) -> Optional[Dict]:
        """Get file state by SHA-256"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("SELECT * FROM file_state WHERE sha256 = %s", (sha256,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_file_by_drive_id(self, drive_file_id: str) -> Optional[Dict]:
        """Get file state by Google Drive file ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(
                "SELECT * FROM file_state WHERE drive_file_id = %s", 
                (drive_file_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_files_by_status(self, status: FileStatus, limit: Optional[int] = None) -> List[Dict]:
        """Get all files with a specific status"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            query = "SELECT * FROM file_state WHERE status = %s ORDER BY updated_at DESC"
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
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                SELECT * FROM file_state 
                WHERE status IN ('processing', 'indexing')
                AND updated_at < NOW() - INTERVAL '%s hours'
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
            now = datetime.utcnow()
            
            for file in stale_files:
                if file["status"] == "processing":
                    new_status = FileStatus.FAILED_PROCESS.value
                else:
                    new_status = FileStatus.FAILED_INDEX.value
                
                cursor.execute("""
                    UPDATE file_state 
                    SET status = %s, 
                        error_message = %s,
                        error_type = 'StaleProcessing',
                        last_error_at = %s,
                        updated_at = %s
                    WHERE sha256 = %s
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
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("SELECT value FROM checkpoint WHERE key = %s", (key,))
            row = cursor.fetchone()
            return row["value"] if row else None
    
    def set_checkpoint(self, key: str, value: str) -> None:
        """Set checkpoint value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow()
            cursor.execute("""
                INSERT INTO checkpoint (key, value, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = EXCLUDED.updated_at
            """, (key, value, now))
    
    # ==================== STATISTICS ====================
    
    def get_statistics(self) -> Dict[str, int]:
        """Get pipeline statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            stats = {}
            
            # Count by status
            for status in FileStatus:
                cursor.execute(
                    "SELECT COUNT(*) as count FROM file_state WHERE status = %s",
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
        from pathlib import Path
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
