"""Google Drive to S3 sync module"""

import hashlib
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from tqdm import tqdm

from .config import Config
from .database import Database, FileStatus
from .utils import S3Client, ProgressTracker, safe_filename, setup_logging


SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
logger = setup_logging(__name__)


def sanitize_metadata_value(value: str) -> str:
    """
    Sanitize metadata values for S3 compatibility.
    
    S3 metadata must contain only ASCII characters. This function URL-encodes
    non-ASCII characters to ensure compatibility while preserving the information.
    """
    import urllib.parse
    
    # Remove control characters (except tab, newline, carriage return)
    cleaned = ''.join(char for char in value if ord(char) >= 32 or char in '\t\n\r')
    
    # S3 metadata must be ASCII-only, so URL-encode non-ASCII characters
    # Use quote_plus to encode spaces and special characters
    # safe=':/' keeps common path separators readable
    encoded = urllib.parse.quote(cleaned, safe='')
    
    return encoded

# Google Workspace MIME types that need export
GOOGLE_MIME_EXPORTS = {
    'application/vnd.google-apps.document': (
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 
        '.docx'
    ),
    'application/vnd.google-apps.presentation': (
        'application/vnd.openxmlformats-officedocument.presentationml.presentation', 
        '.pptx'
    ),
    'application/vnd.google-apps.spreadsheet': (
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
        '.xlsx'
    ),
}


class DriveSync:
    """Sync files from Google Drive to S3"""
    
    def __init__(self, config: Config, database: Database, dry_run: bool = False):
        self.config = config
        self.database = database
        self.dry_run = dry_run
        
        # Initialize Google Drive API
        credentials = service_account.Credentials.from_service_account_file(
            config.google_service_account_file, scopes=SCOPES)
        self.drive_service = build('drive', 'v3', credentials=credentials)
        
        # Initialize S3 client with connection pooling
        self.s3 = S3Client(
            endpoint=config.s3_endpoint,
            access_key=config.s3_access_key,
            secret_key=config.s3_secret_key,
            bucket=config.s3_bucket,
            region=config.s3_region
        )
    
    def get_last_checkpoint(self) -> Optional[str]:
        """Get the last sync checkpoint (RFC3339 timestamp) from database"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would read checkpoint from database")
            return None
        
        try:
            checkpoint = self.database.get_checkpoint('drive_sync_last_modified')
            if checkpoint:
                logger.info(f"📍 Last checkpoint: {checkpoint}")
            else:
                logger.info("📍 No checkpoint found, will sync all files")
            return checkpoint
        except Exception as e:
            logger.info(f"📍 No checkpoint found: {e}")
            return None
    
    def save_checkpoint(self, timestamp: str, silent: bool = False) -> None:
        """Save the sync checkpoint to database"""
        if self.dry_run:
            if not silent:
                logger.info(f"[DRY RUN] Would save checkpoint: {timestamp}")
            return
        
        self.database.set_checkpoint('drive_sync_last_modified', timestamp)
        if not silent:
            logger.info(f"✅ Saved checkpoint: {timestamp}")
    
    def list_files_from_drive(self, max_files: Optional[int] = None, 
                             modified_after: Optional[str] = None):
        """
        Generator that yields files from Google Drive folder and subfolders.
        
        Memory-efficient: processes files one at a time instead of loading all into memory.
        
        Args:
            max_files: Maximum number of files to yield
            modified_after: RFC3339 timestamp to filter by modifiedTime
        
        Yields:
            File metadata dictionaries
        """
        files_yielded = 0
        
        def scan_folder(folder_id: str, path: str = ""):
            """Recursively scan folders and yield files"""
            nonlocal files_yielded
            
            if max_files and files_yielded >= max_files:
                return
            
            query = f"'{folder_id}' in parents and trashed=false"
            if modified_after:
                query += f" and modifiedTime > '{modified_after}'"
            
            try:
                page_token = None
                while True:
                    results = self.drive_service.files().list(
                        q=query,
                        pageSize=100,
                        fields="nextPageToken, files(id, name, mimeType, modifiedTime, createdTime, size, parents)",
                        pageToken=page_token,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                        orderBy='modifiedTime'
                    ).execute()
                    
                    items = results.get('files', [])
                    
                    for item in items:
                        if max_files and files_yielded >= max_files:
                            return
                        
                        item_path = f"{path}/{item['name']}" if path else item['name']
                        item['path'] = item_path
                        
                        # If it's a folder, recurse
                        if item['mimeType'] == 'application/vnd.google-apps.folder':
                            yield from scan_folder(item['id'], item_path)
                        else:
                            # Check if it's a supported file
                            ext = Path(item['name']).suffix.lower()
                            is_google_doc = item['mimeType'] in GOOGLE_MIME_EXPORTS
                            
                            if ext in self.config.additional_extensions or is_google_doc:
                                files_yielded += 1
                                yield item
                    
                    page_token = results.get('nextPageToken')
                    if not page_token:
                        break
            
            except HttpError as error:
                logger.error(f"Error scanning folder {folder_id}: {error}")
        
        # Start scanning from root folder
        yield from scan_folder(self.config.google_drive_folder_id)
    
    def file_already_synced(self, drive_file_id: str, drive_path: str, original_name: str) -> Optional[Tuple[str, bool]]:
        """
        Check if a Drive file ID already exists in database (O(1) lookup).
        
        Args:
            drive_file_id: Google Drive file ID
            drive_path: Current path of file in Drive
            original_name: Current name of file in Drive
        
        Returns:
            Tuple of (S3 key, needs_metadata_update) if file exists, None otherwise
            - needs_metadata_update=True if file was renamed/moved in Drive
        """
        # O(1) database lookup instead of O(N) S3 API calls
        file_record = self.database.get_file_by_drive_id(drive_file_id)
        
        if file_record:
            s3_key = file_record["s3_key"]
            stored_path = file_record.get("drive_path", "")
            stored_name = file_record.get("original_name", "")
            
            # Check if file was renamed or moved
            needs_update = (stored_path != drive_path or stored_name != original_name)
            
            return (s3_key, needs_update)
        
        return None
    
    def download_and_upload_file(self, file_meta: Dict, s3_client: Optional[S3Client] = None) -> Optional[Tuple[str, bool, str]]:
        """
        Download file from Drive and upload to S3
        
        Strategy (optimized for speed):
        1. **First**: Check if Drive file ID exists in database (FAST - no download)
        2. **Second**: Download and compute SHA-256
        3. **Third**: Check if SHA-256 exists in database (content deduplication)
        4. **Finally**: Upload if new, save to database atomically
        
        Args:
            file_meta: File metadata from Drive
            s3_client: Optional S3Client instance (create one per thread to avoid memory corruption)
        
        Returns:
            Tuple of (s3_key, is_new, sha256) if successful, None otherwise
            - is_new=True means newly uploaded, is_new=False means skipped (already exists)
        """
        # Create thread-local clients to avoid memory corruption in concurrent access
        if s3_client is None:
            s3_client = S3Client(
                endpoint=self.config.s3_endpoint,
                access_key=self.config.s3_access_key,
                secret_key=self.config.s3_secret_key,
                bucket=self.config.s3_bucket,
                region=self.config.s3_region
            )
        
        # Create thread-local Drive service (Google API client is NOT thread-safe)
        credentials = service_account.Credentials.from_service_account_file(
            self.config.google_service_account_file, scopes=SCOPES)
        drive_service = build('drive', 'v3', credentials=credentials)
        
        file_id = file_meta['id']
        file_name = file_meta['name']
        mime_type = file_meta['mimeType']
        modified_time = file_meta['modifiedTime']
        created_time = file_meta.get('createdTime', modified_time)
        
        # STEP 1: Check if Drive ID already exists (FAST - no download needed)
        existing_result = self.file_already_synced(file_id, file_meta['path'], file_meta['name'])
        if existing_result:
            existing_key, needs_metadata_update = existing_result
            
            if needs_metadata_update:
                if not self.dry_run:
                    try:
                        # Update S3 metadata without re-uploading file content
                        new_metadata = {
                            'drive-path': sanitize_metadata_value(file_meta['path']),
                            'original-name': sanitize_metadata_value(file_meta['name'])
                        }
                        s3_client.update_object_metadata(existing_key, new_metadata)
                        
                        # Update database with new path/name
                        sha256 = Path(existing_key).stem
                        self.database.upsert_file(
                            sha256=sha256,
                            s3_key=existing_key,
                            status=FileStatus.SYNCED,
                            drive_file_id=file_id,
                            drive_path=file_meta['path'],
                            original_name=file_meta['name']
                        )
                    except Exception as e:
                        logger.debug(f"Failed to update metadata: {e}")
                
                # Extract SHA256 from key: objects/aa/bb/sha256.ext
                sha256 = Path(existing_key).stem
                return (existing_key, False, sha256)
            else:
                # Extract SHA256 from key: objects/aa/bb/sha256.ext
                sha256 = Path(existing_key).stem
                return (existing_key, False, sha256)
        
        logger.debug(f"   Drive ID: {file_id} - not found in database or needs update, downloading...")
        
        # Determine if we need to export (Google Docs/Slides/Sheets)
        is_export = mime_type in GOOGLE_MIME_EXPORTS
        if is_export:
            export_mime, export_ext = GOOGLE_MIME_EXPORTS[mime_type]
            file_name = Path(file_name).stem + export_ext
        
        # Download from Drive
        logger.debug("   📥 Downloading from Drive...")
        if is_export:
            request = drive_service.files().export_media(
                fileId=file_id,
                mimeType=export_mime
            )
        else:
            request = drive_service.files().get_media(fileId=file_id)
        
        # Download to memory
        file_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                logger.debug(f"   Download: {int(status.progress() * 100)}%")
        
        file_buffer.seek(0)
        file_data = file_buffer.getvalue()
        
        # Compute SHA-256
        sha256 = hashlib.sha256(file_data).hexdigest()
        logger.debug(f"   🔑 SHA-256: {sha256[:16]}...")
        
        # Generate CAS key with hash-based sharding: objects/aa/bb/aabbcc...xyz.ext
        # Use first 2 and next 2 chars for directory sharding (like Git)
        extension = Path(file_name).suffix.lower()
        shard1 = sha256[:2]
        shard2 = sha256[2:4]
        s3_key = f"objects/{shard1}/{shard2}/{sha256}{extension}"
        
        # STEP 2: Check if this SHA-256 already exists in database (content-based deduplication)
        existing_by_hash = self.database.get_file_by_sha256(sha256)
        if existing_by_hash:
            logger.info(f"   ⏭️  Content already exists (SHA-256: {sha256[:16]}...), updating Drive mapping")
            
            # Update database to map this Drive ID to existing SHA-256
            if not self.dry_run:
                self.database.upsert_file(
                    sha256=sha256,
                    s3_key=s3_key,
                    status=FileStatus.SYNCED,
                    drive_file_id=file_id,
                    drive_path=file_meta['path'],
                    original_name=file_meta['name'],
                    extension=extension
                )
            
            return (s3_key, False, sha256)  # Return (key, is_new=False, sha256)
        
        logger.debug(f"   S3 key: {s3_key}")
        
        if self.dry_run:
            logger.info(f"   [DRY RUN] Would upload to s3://{self.config.s3_bucket}/{s3_key}")
            return (s3_key, True, sha256)  # Return (key, is_new=True, sha256) for dry run
        
        try:
            # Detect MIME type based on extension
            mime_types = {
                '.pdf': 'application/pdf',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.txt': 'text/plain',
                '.rtf': 'application/rtf',
                '.epub': 'application/epub+zip'
            }
            content_type = mime_types.get(extension, 'application/octet-stream')
            
            # Upload to S3 with minimal metadata (avoid duplication with meta.json later)
            metadata = {
                'sha256': sha256,
                'drive-file-id': file_id,
                'original-name': sanitize_metadata_value(file_meta['name']),
                'drive-path': sanitize_metadata_value(file_meta['path'])
            }
            
            s3_client.put_object(
                key=s3_key,
                data=file_data,
                metadata=metadata,
                content_type=content_type
            )
            
            # Save to database atomically (after successful S3 upload)
            self.database.upsert_file(
                sha256=sha256,
                s3_key=s3_key,
                status=FileStatus.SYNCED,
                drive_file_id=file_id,
                drive_path=file_meta['path'],
                original_name=file_meta['name'],
                extension=extension
            )
            
            return (s3_key, True, sha256)  # Return (key, is_new=True, sha256)
        
        except Exception as e:
            logger.debug(f"Error uploading {file_meta['name']}: {e}")
            
            # Save error to database
            if sha256:
                self.database.upsert_file(
                    sha256=sha256,
                    s3_key=s3_key,
                    status=FileStatus.FAILED_SYNC,
                    drive_file_id=file_id,
                    drive_path=file_meta['path'],
                    original_name=file_meta['name'],
                    extension=extension,
                    error_message=str(e),
                    error_type=type(e).__name__
                )
            
            return None
    
    def sync(self, max_files: Optional[int] = None, force_full: bool = False) -> Tuple[int, int, List[str]]:
        """
        Sync files from Drive to S3 with optional parallel processing
        
        Args:
            max_files: Maximum number of NEW files to sync (not total files to check)
            force_full: Ignore checkpoint and sync all files
        
        Returns:
            Tuple of (successful_count, failed_count, list_of_sha256_hashes)
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        logger.info("="*80)
        logger.info("🚀 Starting Google Drive → S3 Sync")
        if self.dry_run:
            logger.info("   [DRY RUN MODE - No changes will be made]")
        if max_files:
            logger.info(f"   [TARGET: Sync up to {max_files} NEW files]")
        logger.info("="*80)
        
        # Get checkpoint (for logging only - we'll check database for each file)
        # When force_full is specified, ignore checkpoint
        if force_full:
            last_checkpoint = None
            logger.info("   💡 Force full sync: Checking all Drive files")
        else:
            last_checkpoint = self.get_last_checkpoint()
        
        # List files from Drive - generator yields files one at a time (memory-efficient)
        # Don't filter by modified_after - let database lookups handle deduplication
        # This ensures we process ALL unsynced files, not just recently modified ones
        # Don't limit fetch - keep fetching until we have max_files NEW files
        
        files_generator = self.list_files_from_drive(
            max_files=None,  # No fetch limit - keep going until we get enough NEW files
            modified_after=None  # Don't filter - check database instead
        )
        
        # Process files with progress tracking
        # Note: We'll stop after max_files successful NEW uploads
        tracker = ProgressTracker(max_files or 0, "Syncing")
        latest_modified = last_checkpoint
        new_files_synced = 0
        synced_sha256_hashes = []  # Track SHA256 hashes of synced files
        
        # Use parallel processing with ThreadPoolExecutor (I/O bound operations)
        # Using 10 workers for concurrent Drive API calls and S3 uploads
        MAX_WORKERS = 10
        
        # Smaller batch size for better granularity when stopping
        batch_size = 10
        file_batch = []
        
        # Create clean progress bar with proper formatting
        pbar = tqdm(
            total=max_files if max_files else None,
            desc="📥 Syncing",
            unit=" file",
            ncols=100,
            bar_format='{desc}: {n_fmt}/{total_fmt} [{elapsed}] {bar} {postfix}'
        )
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for file_meta in files_generator:
                # Stop if we've reached the max_files limit for NEW files
                if max_files and new_files_synced >= max_files:
                    pbar.write(f"\n✅ Reached target of {max_files} new files, stopping")
                    break
                
                file_batch.append(file_meta)
                
                # Process batch when it reaches batch_size or at the end
                if len(file_batch) >= batch_size:
                    # Submit all tasks in batch
                    future_to_file = {
                        executor.submit(self.download_and_upload_file, file_meta): file_meta
                        for file_meta in file_batch
                    }
                    
                    # Collect results
                    for future in as_completed(future_to_file):
                        # Check if we've already reached the limit
                        if max_files and new_files_synced >= max_files:
                            break
                        
                        file_meta = future_to_file[future]
                        
                        try:
                            result = future.result()
                            
                            # result is either None (failed) or (s3_key, is_new, sha256) tuple
                            if result:
                                s3_key, is_new, sha256 = result
                                tracker.update(success=True)
                                
                                # Track all successfully synced files (new or existing)
                                synced_sha256_hashes.append(sha256)
                                
                                if is_new:
                                    new_files_synced += 1
                                    pbar.update(1)
                                
                                # Track latest modified time and save checkpoint incrementally
                                if not latest_modified or file_meta['modifiedTime'] > latest_modified:
                                    latest_modified = file_meta['modifiedTime']
                                    # Save checkpoint incrementally (every 10 files) - silently
                                    if new_files_synced % 10 == 0 and new_files_synced > 0:
                                        self.save_checkpoint(latest_modified, silent=True)
                                
                                skipped = tracker.successful - new_files_synced
                                pbar.set_postfix_str(f"new={new_files_synced}, skipped={skipped}")
                            else:
                                tracker.update(success=False)
                                skipped = tracker.successful - new_files_synced
                                pbar.set_postfix_str(f"new={new_files_synced}, skipped={skipped}, failed={tracker.failed}")
                            
                        except Exception as e:
                            pbar.write(f"❌ Error: {file_meta.get('name', 'unknown')}: {e}")
                            tracker.update(success=False)
                    
                    # Clear batch
                    file_batch = []
                    
                    # Stop if we've reached the limit after processing this batch
                    if max_files and new_files_synced >= max_files:
                        break
            
            # Process remaining files in the last batch
            if file_batch and (not max_files or new_files_synced < max_files):
                future_to_file = {
                    executor.submit(self.download_and_upload_file, file_meta): file_meta
                    for file_meta in file_batch
                }
                
                for future in as_completed(future_to_file):
                    if max_files and new_files_synced >= max_files:
                        break
                    
                    file_meta = future_to_file[future]
                    
                    try:
                        result = future.result()
                        
                        if result:
                            s3_key, is_new, sha256 = result
                            tracker.update(success=True)
                            synced_sha256_hashes.append(sha256)
                            
                            if is_new:
                                new_files_synced += 1
                                pbar.update(1)
                            
                            if not latest_modified or file_meta['modifiedTime'] > latest_modified:
                                latest_modified = file_meta['modifiedTime']
                            
                            skipped = tracker.successful - new_files_synced
                            pbar.set_postfix_str(f"new={new_files_synced}, skipped={skipped}")
                        else:
                            tracker.update(success=False)
                            skipped = tracker.successful - new_files_synced
                            pbar.set_postfix_str(f"new={new_files_synced}, skipped={skipped}, failed={tracker.failed}")
                        
                    except Exception as e:
                        pbar.write(f"❌ Error: {file_meta.get('name', 'unknown')}: {e}")
                        tracker.update(success=False)
        
        pbar.close()
        
        # Check if no files were found
        if tracker.successful == 0 and tracker.failed == 0:
            if last_checkpoint:
                logger.info(f"✨ No new or modified files since last sync ({last_checkpoint})")
                logger.info("   💡 All files are up to date!")
            else:
                logger.info("✨ No files found in Drive folder")
            return 0, 0, []
        
        # Save final checkpoint
        if latest_modified and tracker.successful > 0:
            self.save_checkpoint(latest_modified)
        
        # Summary
        skipped_count = tracker.successful - new_files_synced
        logger.info("\n" + "="*80)
        logger.info(f"✅ Sync complete: {new_files_synced} new, {skipped_count} skipped, {tracker.failed} failed")
        logger.info("="*80)
        
        return tracker.successful, tracker.failed, synced_sha256_hashes
