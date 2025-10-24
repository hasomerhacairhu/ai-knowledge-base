"""Shared utilities for the ingest pipeline"""

import logging
import sys
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError


# Configure logging
def setup_logging(name: str = __name__, level: str = "INFO") -> logging.Logger:
    """
    Configure logging with consistent formatting
    
    Args:
        name: Logger name (typically __name__ from calling module)
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.INFO)
    
    # Console handler with formatting
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '%(message)s'  # Simple format since we use emojis in messages
    )
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    return logger


class S3Client:
    """Shared S3 client with connection pooling and retry logic"""
    
    def __init__(self, endpoint: str, access_key: str, secret_key: str, 
                 bucket: str, region: str = "us-east-1"):
        """Initialize S3 client with configuration"""
        from botocore.config import Config
        
        self.bucket = bucket
        
        # Configure with connection pooling and retries
        config = Config(
            region_name=region,
            retries={
                'max_attempts': 3,
                'mode': 'adaptive'
            },
            max_pool_connections=50
        )
        
        self.client = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=config
        )
    
    def object_exists(self, key: str) -> bool:
        """Check if object exists in S3"""
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False
    
    def get_object(self, key: str) -> tuple[bytes, dict]:
        """
        Get object data and metadata
        
        Returns:
            Tuple of (data, metadata)
        """
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        data = response['Body'].read()
        metadata = response.get('Metadata', {})
        return data, metadata
    
    def get_object_metadata(self, key: str) -> tuple[dict, dict]:
        """
        Get object metadata without downloading the content (HeadObject)
        This is much faster than get_object for just checking metadata.
        
        Returns:
            Tuple of (response_headers, metadata)
        """
        response = self.client.head_object(Bucket=self.bucket, Key=key)
        metadata = response.get('Metadata', {})
        return response, metadata
    
    def put_object(self, key: str, data: bytes, metadata: Optional[dict] = None, 
                   content_type: Optional[str] = None) -> None:
        """Upload object to S3 with optional metadata and content type"""
        kwargs = {
            'Bucket': self.bucket,
            'Key': key,
            'Body': data
        }
        if metadata:
            kwargs['Metadata'] = metadata
        if content_type:
            kwargs['ContentType'] = content_type
        
        self.client.put_object(**kwargs)
    
    def update_object_metadata(self, key: str, metadata: dict) -> None:
        """
        Update object metadata without re-uploading the file content.
        Uses S3 CopyObject with metadata replacement.
        
        Args:
            key: S3 object key
            metadata: New metadata dict (will be merged with existing SHA-256)
        """
        # Get current metadata to preserve sha256
        _, current_metadata = self.get_object_metadata(key)
        
        # Merge metadata, preserving sha256
        merged_metadata = {
            'sha256': current_metadata.get('sha256', ''),
            'drive-file-id': current_metadata.get('drive-file-id', '')
        }
        merged_metadata.update(metadata)
        
        # Get content type from current object
        response, _ = self.get_object_metadata(key)
        content_type = response.get('ContentType', 'application/octet-stream')
        
        # Copy object to itself with new metadata (metadata-only update)
        self.client.copy_object(
            Bucket=self.bucket,
            CopySource={'Bucket': self.bucket, 'Key': key},
            Key=key,
            Metadata=merged_metadata,
            ContentType=content_type,
            MetadataDirective='REPLACE'
        )
    
    def copy_object(self, source_key: str, dest_key: str) -> None:
        """Copy object within bucket"""
        self.client.copy_object(
            Bucket=self.bucket,
            CopySource={'Bucket': self.bucket, 'Key': source_key},
            Key=dest_key
        )
    
    def delete_object(self, key: str) -> None:
        """Delete object from S3"""
        self.client.delete_object(Bucket=self.bucket, Key=key)
    
    def list_objects(self, prefix: str, max_keys: Optional[int] = None) -> list[str]:
        """
        List object keys with given prefix
        
        Returns:
            List of object keys (strings)
        """
        keys = []
        paginator = self.client.get_paginator('list_objects_v2')
        
        page_kwargs = {'Bucket': self.bucket, 'Prefix': prefix}
        if max_keys:
            page_kwargs['MaxKeys'] = max_keys
        
        for page in paginator.paginate(**page_kwargs):
            for obj in page.get('Contents', []):
                keys.append(obj['Key'])
                if max_keys and len(keys) >= max_keys:
                    return keys
        
        return keys


def format_bytes(size_bytes: int) -> str:
    """Format bytes to human-readable size"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def safe_filename(filename: str) -> str:
    """Convert filename to safe ASCII-only version (no special chars, no accents)"""
    import re
    import unicodedata
    
    # Normalize unicode and convert to ASCII (removes accents)
    normalized = unicodedata.normalize('NFKD', filename)
    ascii_str = normalized.encode('ascii', 'ignore').decode('ascii')
    
    # Replace unsafe characters with underscore
    safe = re.sub(r'[^\w.-]', '_', ascii_str)
    # Replace multiple underscores/spaces with single underscore
    safe = re.sub(r'_+', '_', safe)
    return safe.strip('_')


def ensure_directory(path: Path) -> None:
    """Ensure directory exists"""
    path.mkdir(parents=True, exist_ok=True)


class ProgressTracker:
    """Track and display progress for batch operations"""
    
    def __init__(self, total: int, description: str = "Processing"):
        self.total = total
        self.current = 0
        self.description = description
        self.successful = 0
        self.failed = 0
    
    def update(self, success: bool = True) -> None:
        """Update progress"""
        self.current += 1
        if success:
            self.successful += 1
        else:
            self.failed += 1
    
    def __str__(self) -> str:
        """String representation of progress"""
        percentage = (self.current / self.total * 100) if self.total > 0 else 0
        return (f"{self.description}: [{self.current}/{self.total}] "
                f"({percentage:.1f}%) - ✅ {self.successful} | ❌ {self.failed}")
