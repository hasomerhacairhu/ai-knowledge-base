"""
Purge script - Deletes all data from S3 bucket and database

WARNING: This is a destructive operation that cannot be undone!
Use with caution, especially in production environments.
"""

import argparse
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.database import Database
from src.utils import S3Client, setup_logging

logger = setup_logging(__name__)


def purge_s3(s3_client: S3Client, bucket: str, dry_run: bool = False) -> int:
    """
    Delete all objects from S3 bucket, including all versions if versioning is enabled
    
    Args:
        s3_client: Initialized S3Client
        bucket: Bucket name
        dry_run: If True, only show what would be deleted
    
    Returns:
        Number of objects deleted
    """
    logger.info("="*80)
    logger.info("🗑️  PURGING S3 BUCKET")
    if dry_run:
        logger.info("   [DRY RUN MODE - No changes will be made]")
    logger.info("="*80)
    
    # Check if versioning is enabled
    try:
        versioning = s3_client.client.get_bucket_versioning(Bucket=bucket)
        versioning_enabled = versioning.get('Status') == 'Enabled'
        
        if versioning_enabled:
            logger.info(f"\n⚠️  Bucket versioning is ENABLED")
            logger.info("   Will delete all object versions and delete markers")
        else:
            logger.info(f"\n📋 Bucket versioning is not enabled")
    except Exception as e:
        logger.warning(f"⚠️  Could not check versioning status: {e}")
        versioning_enabled = False
    
    # List all objects
    logger.info(f"\n📋 Listing objects in bucket: {bucket}")
    
    try:
        total_objects = 0
        deleted_count = 0
        
        if versioning_enabled:
            # Delete all versions and delete markers
            paginator = s3_client.client.get_paginator('list_object_versions')
            pages = paginator.paginate(Bucket=bucket)
            
            for page in pages:
                # Collect both versions and delete markers
                versions = page.get('Versions', [])
                delete_markers = page.get('DeleteMarkers', [])
                all_items = versions + delete_markers
                
                if not all_items:
                    continue
                
                total_objects += len(all_items)
                
                if dry_run:
                    logger.info(f"   Would delete {len(versions)} versions and {len(delete_markers)} delete markers from this page")
                    for item in all_items:
                        version_id = item.get('VersionId', 'null')
                        is_delete_marker = 'IsLatest' in item and item.get('Key') in [dm['Key'] for dm in delete_markers]
                        marker_flag = " (delete marker)" if is_delete_marker else ""
                        logger.debug(f"   - {item['Key']} [version: {version_id}]{marker_flag}")
                else:
                    # Delete in batches of 1000 (S3 limit)
                    batch = [{'Key': item['Key'], 'VersionId': item['VersionId']} for item in all_items]
                    
                    if batch:
                        response = s3_client.client.delete_objects(
                            Bucket=bucket,
                            Delete={'Objects': batch}
                        )
                        
                        deleted = len(response.get('Deleted', []))
                        errors = response.get('Errors', [])
                        
                        deleted_count += deleted
                        
                        logger.info(f"   ✅ Deleted {deleted} object versions/markers")
                        
                        if errors:
                            logger.error(f"   ❌ Failed to delete {len(errors)} items:")
                            for error in errors:
                                logger.error(f"      - {error['Key']} [version: {error.get('VersionId', 'unknown')}]: {error['Message']}")
        else:
            # Standard deletion (no versioning)
            paginator = s3_client.client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket)
            
            for page in pages:
                if 'Contents' not in page:
                    continue
                
                objects = page['Contents']
                total_objects += len(objects)
                
                if dry_run:
                    logger.info(f"   Would delete {len(objects)} objects from this page")
                    for obj in objects:
                        logger.debug(f"   - {obj['Key']}")
                else:
                    # Delete in batches of 1000 (S3 limit)
                    batch = [{'Key': obj['Key']} for obj in objects]
                    
                    if batch:
                        response = s3_client.client.delete_objects(
                            Bucket=bucket,
                            Delete={'Objects': batch}
                        )
                        
                        deleted = len(response.get('Deleted', []))
                        errors = response.get('Errors', [])
                        
                        deleted_count += deleted
                        
                        logger.info(f"   ✅ Deleted {deleted} objects")
                        
                        if errors:
                            logger.error(f"   ❌ Failed to delete {len(errors)} objects:")
                            for error in errors:
                                logger.error(f"      - {error['Key']}: {error['Message']}")
        
        logger.info("\n" + "="*80)
        if dry_run:
            logger.info(f"✅ Would delete {total_objects} objects from S3 bucket")
        else:
            logger.info(f"✅ Deleted {deleted_count} objects from S3 bucket")
        logger.info("="*80)
        
        return deleted_count if not dry_run else total_objects
    
    except Exception as e:
        logger.error(f"❌ Error purging S3: {e}")
        import traceback
        traceback.print_exc()
        return 0


def purge_database(db_path: str, dry_run: bool = False) -> bool:
    """
    Delete the database file
    
    Args:
        db_path: Path to database file
        dry_run: If True, only show what would be deleted
    
    Returns:
        True if successful
    """
    logger.info("\n" + "="*80)
    logger.info("🗑️  PURGING DATABASE")
    if dry_run:
        logger.info("   [DRY RUN MODE - No changes will be made]")
    logger.info("="*80)
    
    db_file = Path(db_path)
    
    if not db_file.exists():
        logger.info(f"\n⚠️  Database file does not exist: {db_path}")
        return True
    
    try:
        if dry_run:
            logger.info(f"\n   Would delete database file: {db_path}")
            file_size = db_file.stat().st_size
            logger.info(f"   File size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")
        else:
            # Get file size before deletion
            file_size = db_file.stat().st_size
            
            # Delete the file
            db_file.unlink()
            
            logger.info(f"\n✅ Deleted database file: {db_path}")
            logger.info(f"   File size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")
        
        logger.info("="*80)
        return True
    
    except Exception as e:
        logger.error(f"❌ Error deleting database: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Purge script - Delete all data from S3 bucket and database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
WARNING: This is a destructive operation that cannot be undone!

Examples:
  # Dry run - see what would be deleted
  python purge.py --dry-run

  # Purge only S3 bucket
  python purge.py --s3-only

  # Purge only database
  python purge.py --db-only

  # Purge everything (requires confirmation)
  python purge.py

  # Purge everything without confirmation (dangerous!)
  python purge.py --yes
        """
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - show what would be deleted without making changes"
    )
    
    parser.add_argument(
        "--s3-only",
        action="store_true",
        help="Only purge S3 bucket, leave database intact"
    )
    
    parser.add_argument(
        "--db-only",
        action="store_true",
        help="Only purge database, leave S3 bucket intact"
    )
    
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt (dangerous!)"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    try:
        config = Config.from_env()
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print("\nPlease check your .env file. See .env.example for reference.")
        sys.exit(1)
    
    # Determine what to purge
    purge_s3_flag = not args.db_only
    purge_db_flag = not args.s3_only
    
    # Show warning and ask for confirmation
    if not args.dry_run and not args.yes:
        print("\n" + "="*80)
        print("⚠️  WARNING: DESTRUCTIVE OPERATION")
        print("="*80)
        
        if purge_s3_flag and purge_db_flag:
            print("\nThis will DELETE ALL data from:")
            print(f"  - S3 Bucket: {config.s3_bucket}")
            print(f"  - Database: {config.database_path}")
        elif purge_s3_flag:
            print(f"\nThis will DELETE ALL objects from S3 bucket: {config.s3_bucket}")
        elif purge_db_flag:
            print(f"\nThis will DELETE the database file: {config.database_path}")
        
        print("\n⚠️  This operation CANNOT be undone!")
        print("="*80)
        
        response = input("\nType 'DELETE' to confirm: ")
        
        if response != "DELETE":
            print("\n❌ Operation cancelled")
            sys.exit(0)
    
    # Initialize clients
    if purge_s3_flag:
        s3_client = S3Client(
            endpoint=config.s3_endpoint,
            access_key=config.s3_access_key,
            secret_key=config.s3_secret_key,
            bucket=config.s3_bucket,
            region=config.s3_region
        )
    
    # Execute purge operations
    print("\n" + "="*80)
    print("🚀 STARTING PURGE OPERATION")
    if args.dry_run:
        print("   [DRY RUN MODE - No changes will be made]")
    print("="*80)
    
    success = True
    
    if purge_s3_flag:
        deleted_count = purge_s3(s3_client, config.s3_bucket, dry_run=args.dry_run)
        if deleted_count == 0 and not args.dry_run:
            success = False
    
    if purge_db_flag:
        db_success = purge_database(config.database_path, dry_run=args.dry_run)
        if not db_success:
            success = False
    
    # Final summary
    print("\n" + "="*80)
    if args.dry_run:
        print("✅ DRY RUN COMPLETE - No changes were made")
    elif success:
        print("✅ PURGE COMPLETE")
    else:
        print("⚠️  PURGE COMPLETED WITH ERRORS")
    print("="*80 + "\n")
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
