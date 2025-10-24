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
from .utils import S3Client, ProgressTracker, safe_filename, setup_logging


SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
logger = setup_logging(__name__)


def sanitize_metadata_value(value: str) -> str:
    """
    Sanitize metadata values for S3 compatibility.
    
    S3 metadata supports UTF-8, but we need to ensure proper encoding.
    Uses URL encoding for special characters while preserving readability.
    """
    import urllib.parse
    
    # S3 metadata values must be valid UTF-8 and cannot contain certain control characters
    # Remove control characters but preserve unicode text
    cleaned = ''.join(char for char in value if ord(char) >= 32 or char in '\t\n\r')
    
    # Return cleaned UTF-8 string (S3 will handle encoding)
    return cleaned

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
    
    def __init__(self, config: Config, dry_run: bool = False):
        self.config = config
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
        
        # Track checkpoint
        self.checkpoint_key = 'checkpoints/drive_sync_last_modified.txt'
        self.manifest_key = 'checkpoints/drive_id_manifest.json'
        self._manifest_cache = None  # In-memory cache of Drive ID → S3 key mapping
    
    def get_last_checkpoint(self) -> Optional[str]:
        """Get the last sync checkpoint (RFC3339 timestamp)"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would read checkpoint from {self.checkpoint_key}")
            return None
        
        try:
            data, _ = self.s3.get_object(self.checkpoint_key)
            checkpoint = data.decode('utf-8').strip()
            logger.info(f"📍 Last checkpoint: {checkpoint}")
            return checkpoint
        except Exception as e:
            logger.info("📍 No checkpoint found, will sync all files")
            return None
    
    def load_manifest(self) -> Dict[str, Dict[str, str]]:
        """
        Load Drive ID manifest from S3 for O(1) lookups.
        
        Manifest structure:
        {
            "drive-file-id-1": {
                "s3_key": "objects/aa/bb/sha256.pdf",
                "drive_path": "/folder/file.pdf",
                "original_name": "file.pdf"
            },
            ...
        }
        
        Returns:
            Dict mapping Drive file IDs to their metadata
        """
        if self._manifest_cache is not None:
            return self._manifest_cache
        
        if self.dry_run:
            logger.debug(f"[DRY RUN] Would load manifest from {self.manifest_key}")
            self._manifest_cache = {}
            return self._manifest_cache
        
        try:
            data, _ = self.s3.get_object(self.manifest_key)
            manifest = json.loads(data.decode('utf-8'))
            logger.debug(f"📋 Loaded manifest with {len(manifest)} entries")
            self._manifest_cache = manifest
            return manifest
        except Exception as e:
            logger.debug(f"📋 No manifest found, will build from scratch: {e}")
            self._manifest_cache = {}
            return self._manifest_cache
    
    def save_manifest(self, manifest: Dict[str, Dict[str, str]]) -> None:
        """
        Save Drive ID manifest to S3.
        
        Args:
            manifest: Dict mapping Drive file IDs to metadata
        """
        if self.dry_run:
            logger.debug(f"[DRY RUN] Would save manifest with {len(manifest)} entries")
            return
        
        try:
            manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
            self.s3.put_object(
                key=self.manifest_key,
                data=manifest_json.encode('utf-8'),
                content_type='application/json'
            )
            logger.debug(f"✅ Saved manifest with {len(manifest)} entries")
            self._manifest_cache = manifest
        except Exception as e:
            logger.error(f"❌ Failed to save manifest: {e}")
    
    def update_manifest_entry(self, drive_file_id: str, s3_key: str, 
                             drive_path: str, original_name: str) -> None:
        """
        Update a single entry in the manifest (in memory, call save_manifest to persist).
        
        Args:
            drive_file_id: Google Drive file ID
            s3_key: S3 object key
            drive_path: Current path in Drive
            original_name: Current filename in Drive
        """
        if self._manifest_cache is None:
            self._manifest_cache = self.load_manifest()
        
        self._manifest_cache[drive_file_id] = {
            "s3_key": s3_key,
            "drive_path": drive_path,
            "original_name": original_name
        }
    
    def save_checkpoint(self, timestamp: str) -> None:
        """Save the sync checkpoint"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would save checkpoint: {timestamp}")
            return
        
        self.s3.put_object(
            key=self.checkpoint_key,
            data=timestamp.encode('utf-8'),
            content_type='text/plain'
        )
        logger.info(f"✅ Saved checkpoint: {timestamp}")
    
    def list_files_from_drive(self, max_files: Optional[int] = None, 
                             modified_after: Optional[str] = None) -> List[Dict]:
        """
        List files from Google Drive folder and subfolders
        
        Args:
            max_files: Maximum number of files to return
            modified_after: RFC3339 timestamp to filter by modifiedTime
        
        Returns:
            List of file metadata dictionaries
        """
        logger.info(f"🔍 Scanning Google Drive folder: {self.config.google_drive_folder_id}")
        if modified_after:
            logger.info(f"   📅 Modified after: {modified_after}")
        if max_files:
            logger.info(f"   📊 Max files: {max_files}")
        
        all_files = []
        
        def scan_folder(folder_id: str, path: str = "") -> None:
            """Recursively scan folders"""
            if max_files and len(all_files) >= max_files:
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
                        if max_files and len(all_files) >= max_files:
                            return
                        
                        item_path = f"{path}/{item['name']}" if path else item['name']
                        item['path'] = item_path
                        
                        # If it's a folder, recurse
                        if item['mimeType'] == 'application/vnd.google-apps.folder':
                            scan_folder(item['id'], item_path)
                        else:
                            # Check if it's a supported file
                            ext = Path(item['name']).suffix.lower()
                            is_google_doc = item['mimeType'] in GOOGLE_MIME_EXPORTS
                            
                            if ext in self.config.additional_extensions or is_google_doc:
                                all_files.append(item)
                    
                    page_token = results.get('nextPageToken')
                    if not page_token:
                        break
            
            except HttpError as error:
                logger.error(f"Error scanning folder {folder_id}: {error}")
        
        # Start scanning from root folder
        scan_folder(self.config.google_drive_folder_id)
        
        logger.info(f"✅ Found {len(all_files)} supported files")
        return all_files
    
    def file_already_synced(self, drive_file_id: str, drive_path: str, original_name: str) -> Optional[Tuple[str, bool]]:
        """
        Check if a Drive file ID already exists in S3 using the manifest (O(1) lookup).
        
        Args:
            drive_file_id: Google Drive file ID
            drive_path: Current path of file in Drive
            original_name: Current name of file in Drive
        
        Returns:
            Tuple of (S3 key, needs_metadata_update) if file exists, None otherwise
            - needs_metadata_update=True if file was renamed/moved in Drive
        """
        manifest = self.load_manifest()
        
        # O(1) dictionary lookup instead of O(N) S3 API calls
        if drive_file_id in manifest:
            entry = manifest[drive_file_id]
            s3_key = entry["s3_key"]
            stored_path = entry.get("drive_path", "")
            stored_name = entry.get("original_name", "")
            
            # Check if file was renamed or moved
            needs_update = (stored_path != drive_path or stored_name != original_name)
            
            return (s3_key, needs_update)
        
        return None
    
    def download_and_upload_file(self, file_meta: Dict) -> Optional[Tuple[str, bool, str]]:
        """
        Download file from Drive and upload to S3
        
        Strategy (optimized for speed):
        1. **First**: Check if Drive file ID exists in S3 metadata (FAST - no download)
        2. **Second**: Download and compute SHA-256
        3. **Third**: Check if SHA-256 exists in S3 (content deduplication)
        4. **Finally**: Upload if new
        
        Returns:
            Tuple of (s3_key, is_new, sha256) if successful, None otherwise
            - is_new=True means newly uploaded, is_new=False means skipped (already exists)
        """
        file_id = file_meta['id']
        file_name = file_meta['name']
        mime_type = file_meta['mimeType']
        modified_time = file_meta['modifiedTime']
        created_time = file_meta.get('createdTime', modified_time)
        
        # Use tqdm.write() for progress bar compatibility
        from tqdm import tqdm
        tqdm.write(f"📥 {file_meta['path']}")
        
        # STEP 1: Check if Drive ID already exists (FAST - no download needed)
        existing_result = self.file_already_synced(file_id, file_meta['path'], file_meta['name'])
        if existing_result:
            existing_key, needs_metadata_update = existing_result
            
            if needs_metadata_update:
                tqdm.write(f"   🔄 File renamed/moved in Drive, updating metadata...")
                
                if not self.dry_run:
                    try:
                        # Update S3 metadata without re-uploading file content
                        new_metadata = {
                            'drive-path': sanitize_metadata_value(file_meta['path']),
                            'original-name': sanitize_metadata_value(file_meta['name'])
                        }
                        self.s3.update_object_metadata(existing_key, new_metadata)
                        
                        # Update manifest with new path/name
                        self.update_manifest_entry(file_id, existing_key, file_meta['path'], file_meta['name'])
                        
                        tqdm.write(f"   ✅ Metadata updated (path: {file_meta['path']})")
                    except Exception as e:
                        logger.error(f"   ❌ Failed to update metadata: {e}")
                else:
                    tqdm.write(f"   [DRY RUN] Would update metadata for {existing_key}")
                
                # Extract SHA256 from key: objects/aa/bb/sha256.ext
                sha256 = Path(existing_key).stem
                return (existing_key, False, sha256)
            else:
                tqdm.write(f"   ⏭️  Already synced (Drive ID: {file_id[:12]}...), skipping")
                # Extract SHA256 from key: objects/aa/bb/sha256.ext
                sha256 = Path(existing_key).stem
                return (existing_key, False, sha256)
        
        logger.debug(f"   Drive ID: {file_id} - not found in S3 or needs update, downloading...")
        
        # Determine if we need to export (Google Docs/Slides/Sheets)
        is_export = mime_type in GOOGLE_MIME_EXPORTS
        if is_export:
            export_mime, export_ext = GOOGLE_MIME_EXPORTS[mime_type]
            file_name = Path(file_name).stem + export_ext
        
        # Download from Drive
        logger.debug("   📥 Downloading from Drive...")
        if is_export:
            request = self.drive_service.files().export_media(
                fileId=file_id,
                mimeType=export_mime
            )
        else:
            request = self.drive_service.files().get_media(fileId=file_id)
        
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
        
        # Check if this SHA-256 already exists (content-based deduplication)
        if not self.dry_run and self.s3.object_exists(s3_key):
            logger.info(f"   ⏭️  Content already exists (SHA-256: {sha256[:16]}...), skipping")
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
            
            self.s3.put_object(
                key=s3_key,
                data=file_data,
                metadata=metadata,
                content_type=content_type
            )
            
            # Update manifest with new entry
            self.update_manifest_entry(file_id, s3_key, file_meta['path'], file_meta['name'])
            
            logger.info(f"   ✅ Uploaded to S3")
            return (s3_key, True, sha256)  # Return (key, is_new=True, sha256)
        
        except Exception as e:
            logger.error(f"   ❌ Error: {e}")
            return None
    
    def sync(self, max_files: Optional[int] = None, force_full: bool = False) -> Tuple[int, int, List[str]]:
        """
        Sync files from Drive to S3
        
        Args:
            max_files: Maximum number of NEW files to sync (not total files to check)
            force_full: Ignore checkpoint and sync all files
        
        Returns:
            Tuple of (successful_count, failed_count, list_of_sha256_hashes)
        """
        logger.info("="*80)
        logger.info("🚀 Starting Google Drive → S3 Sync")
        if self.dry_run:
            logger.info("   [DRY RUN MODE - No changes will be made]")
        if max_files:
            logger.info(f"   [TARGET: Sync up to {max_files} NEW files]")
        logger.info("="*80)
        
        # Get checkpoint - but DON'T use it when max_files is specified
        # When user specifies max_files, they want to process files regardless of checkpoint
        # The SHA-256 check will handle deduplication
        if max_files or force_full:
            last_checkpoint = None
            if max_files:
                logger.info("   💡 Checking all Drive files (SHA-256 deduplication will skip existing)")
        else:
            last_checkpoint = self.get_last_checkpoint()
        
        # List MORE files from Drive than max_files (to account for already-synced files)
        # Multiply by 5 to have enough buffer for deduplication
        fetch_limit = (max_files * 5) if max_files else None
        
        files = self.list_files_from_drive(
            max_files=fetch_limit,
            modified_after=last_checkpoint
        )
        
        if not files:
            if last_checkpoint:
                logger.info(f"✨ No new or modified files since last sync ({last_checkpoint})")
                logger.info("   💡 All files are up to date!")
            else:
                logger.info("✨ No files found in Drive folder")
            return 0, 0, []
        
        # Process files with progress tracking
        # Note: We'll stop after max_files successful NEW uploads
        tracker = ProgressTracker(len(files), "Syncing")
        latest_modified = last_checkpoint
        new_files_synced = 0
        synced_sha256_hashes = []  # Track SHA256 hashes of synced files
        
        # Use tqdm but update total as we go (since we might not process all files)
        with tqdm(desc="📥 Syncing files", unit="file") as pbar:
            for file_meta in files:
                # Stop if we've reached the max_files limit for NEW files
                if max_files and new_files_synced >= max_files:
                    logger.info(f"\n✅ Reached target of {max_files} new files, stopping")
                    break
                
                result = self.download_and_upload_file(file_meta)
                
                # result is either None (failed) or (s3_key, is_new, sha256) tuple
                if result:
                    s3_key, is_new, sha256 = result
                    tracker.update(success=True)
                    
                    # Track all successfully synced files (new or existing)
                    synced_sha256_hashes.append(sha256)
                    
                    if is_new:
                        new_files_synced += 1
                    
                    # Track latest modified time
                    if not latest_modified or file_meta['modifiedTime'] > latest_modified:
                        latest_modified = file_meta['modifiedTime']
                    
                    skipped = tracker.successful - new_files_synced
                    pbar.set_postfix_str(f"✅ {new_files_synced} new | ⏭️  {skipped} skipped")
                else:
                    tracker.update(success=False)
                    skipped = tracker.successful - new_files_synced
                    pbar.set_postfix_str(f"✅ {new_files_synced} new | ⏭️  {skipped} skipped | ❌ {tracker.failed} failed")
                
                pbar.update(1)
        
        # Save checkpoint
        if latest_modified and tracker.successful > 0:
            self.save_checkpoint(latest_modified)
        
        # Save manifest after sync (persist any updates)
        if self._manifest_cache is not None and tracker.successful > 0:
            self.save_manifest(self._manifest_cache)
        
        # Summary
        skipped_count = tracker.successful - new_files_synced
        logger.info("\n" + "="*80)
        logger.info(f"✅ Sync complete: {new_files_synced} new, {skipped_count} skipped, {tracker.failed} failed")
        logger.info("="*80)
        
        return tracker.successful, tracker.failed, synced_sha256_hashes
