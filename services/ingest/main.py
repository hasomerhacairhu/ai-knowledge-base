"""
AI Knowledge Base Ingest Pipeline
Main entry point for the document ingestion workflow
"""

import argparse
import sys
import warnings
import os
from pathlib import Path
import atexit
from concurrent.futures import ProcessPoolExecutor

# Suppress all deprecation and compatibility warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', message='.*deprecated.*')
warnings.filterwarnings('ignore', message='.*max_size.*')

# Suppress PIL/Pillow deprecation warnings at environment level
os.environ['PYTHONWARNINGS'] = 'ignore::DeprecationWarning,ignore::FutureWarning'

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.database import Database
from src.drive_sync import DriveSync
from src.processor import UnstructuredProcessor
from src.indexer import VectorStoreIndexer


def main():
    # Load configuration first to get defaults
    try:
        config = Config.from_env()
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print("\nPlease check your .env file. See .env.example for reference.")
        sys.exit(1)
    
    parser = argparse.ArgumentParser(
        description="AI Knowledge Base Ingest Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - sync 5 files from Drive
  python main.py --dry-run --max-files 5 sync

  # Sync files from Drive to S3
  python main.py --max-files 10 sync

  # Process files from S3 with Unstructured
  python main.py --max-files 5 process

  # Retry previously failed files
  python main.py --retry-failed process

  # Index processed files to Vector Store
  python main.py --max-files 5 index

  # Run full pipeline (sync + process + index)
  python main.py --max-files 10 full

  # Production run without limits
  python main.py full
        """
    )
    
    parser.add_argument(
        "command",
        nargs="?",
        choices=["sync", "process", "index", "full", "migrate", "stats", "cleanup"],
        default="full",
        help="Command to run: sync (Drive→S3), process (S3→Unstructured), index (→Vector Store), full (all), migrate (S3→Database), stats (show statistics), cleanup (clean stale files). Default: full"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - no changes will be made"
    )
    
    parser.add_argument(
        "--max-files",
        type=int,
        default=config.max_files_per_run,
        help=f"Maximum number of files to process (default from .env: {config.max_files_per_run})"
    )
    
    parser.add_argument(
        "--force-full-sync",
        action="store_true",
        help="Ignore checkpoint and sync all files from Drive"
    )
    
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry processing files that previously failed (process command only)"
    )
    
    parser.add_argument(
        "--processor-workers",
        type=int,
        help=f"Number of parallel workers for processing (default from .env: {config.processor_max_workers})"
    )
    
    parser.add_argument(
        "--indexer-workers",
        type=int,
        help=f"Number of parallel workers for indexing (default from .env: {config.indexer_max_workers})"
    )
    
    parser.add_argument(
        "--use-processes",
        action="store_true",
        help="Use ProcessPoolExecutor for CPU-bound tasks (better for OCR-heavy workloads)"
    )
    
    parser.add_argument(
        "--max-stale-hours",
        type=int,
        default=24,
        help="Maximum hours before considering files stale (default: 24)"
    )
    
    args = parser.parse_args()
    
    try:
        # Apply max_files from CLI (already has correct default from config)
        config.max_files_per_run = args.max_files
        
        # Apply worker overrides from CLI
        if args.processor_workers:
            config.processor_max_workers = args.processor_workers
        if args.indexer_workers:
            config.indexer_max_workers = args.indexer_workers
        
        # Initialize database (PostgreSQL)
        database = Database(
            host=config.postgres_host,
            port=config.postgres_port,
            database=config.postgres_db,
            user=config.postgres_user,
            password=config.postgres_password
        )
        
        # Handle special commands
        if args.command == "migrate":
            print("\n" + "="*80)
            print("🔄 MIGRATING S3 STATE TO DATABASE")
            print("="*80)
            
            # Initialize S3 client
            from src.utils import S3Client
            s3_client = S3Client(
                endpoint=config.s3_endpoint,
                access_key=config.s3_access_key,
                secret_key=config.s3_secret_key,
                bucket=config.s3_bucket,
                region=config.s3_region
            )
            
            synced, processed, indexed = database.migrate_from_s3_markers(
                s3_client, 
                config.s3_bucket,
                dry_run=args.dry_run
            )
            
            print("="*80)
            print(f"✅ Migration complete: {synced} synced, {processed} processed, {indexed} indexed")
            print("="*80 + "\n")
            return
        
        if args.command == "stats":
            print("\n" + "="*80)
            print("📊 PIPELINE STATISTICS")
            print("="*80)
            
            stats = database.get_statistics()
            print(f"\n📁 Total files: {stats['total']}")
            print(f"\n📥 Synced: {stats['synced']}")
            print(f"🔄 Processing: {stats['processing']}")
            print(f"✅ Processed: {stats['processed']}")
            print(f"📚 Indexing: {stats['indexing']}")
            print(f"✨ Indexed: {stats['indexed']}")
            print(f"\n❌ Failed:")
            print(f"   - Sync: {stats['failed_sync']}")
            print(f"   - Process: {stats['failed_process']}")
            print(f"   - Index: {stats['failed_index']}")
            print(f"\n⚠️  Files with errors: {stats['with_errors']}")
            
            print("="*80 + "\n")
            return
        
        if args.command == "cleanup":
            print("\n" + "="*80)
            print("🧹 CLEANING UP STALE FILES")
            print("="*80)
            
            stale_count = database.mark_stale_as_failed(max_age_hours=args.max_stale_hours)
            
            print(f"✅ Marked {stale_count} stale files as failed")
            print("="*80 + "\n")
            return
        
        # Initialize components
        drive_sync = DriveSync(config, database, dry_run=args.dry_run)
        processor = UnstructuredProcessor(config, database, dry_run=args.dry_run, use_processes=args.use_processes)
        indexer = VectorStoreIndexer(config, database, dry_run=args.dry_run)
        
        print("\n" + "="*80)
        print("🚀 AI KNOWLEDGE BASE INGEST PIPELINE")
        if args.dry_run:
            print("   [DRY RUN MODE - No changes will be made]")
        if args.max_files:
            print(f"   [TEST MODE - Max {args.max_files} files per stage]")
        print("="*80)
        
        # Run selected command
        if args.command == "sync" or args.command == "full":
            print("\n📥 STAGE 1: Drive → S3 Sync")
            print("-" * 80)
            success, failed, synced_hashes = drive_sync.sync(
                max_files=args.max_files,
                force_full=args.force_full_sync
            )
            print(f"\n✅ Sync: {success} successful, {failed} failed\n")
            # NOTE: synced_hashes is intentionally not passed to the next stage.
            # This is part of a "self-healing" design where each pipeline stage
            # processes ALL pending files (not just newly synced ones). This ensures
            # that files which failed in previous runs are automatically retried.
        else:
            synced_hashes = []
        
        if args.command == "process" or args.command == "full":
            print("\n🔄 STAGE 2: Unstructured Processing")
            print("-" * 80)
            # In full mode, process ALL pending files (including failed ones) for self-healing
            # This ensures files that failed in previous runs are automatically retried
            if args.command == "full":
                # Process all SYNCED files (including newly synced and any orphaned from previous runs)
                # Also retry any FAILED_PROCESS files automatically
                success, failed, processed_hashes = processor.process_batch(
                    max_files=args.max_files,
                    retry_failed=True,  # Auto-retry failed files in full mode
                    filter_sha256=None  # Process all pending, not just newly synced (self-healing)
                )
            else:
                # In standalone process mode, respect the --retry-failed flag
                success, failed, processed_hashes = processor.process_batch(
                    max_files=args.max_files,
                    retry_failed=args.retry_failed,
                    filter_sha256=None
                )
            print(f"\n✅ Process: {success} successful, {failed} failed\n")
            # NOTE: processed_hashes is intentionally not passed to the next stage.
            # This is part of a "self-healing" design where each pipeline stage
            # processes ALL pending files (not just newly processed ones). This ensures
            # that files which were processed but failed indexing are automatically retried.
        else:
            processed_hashes = []
        
        if args.command == "index" or args.command == "full":
            print("\n📚 STAGE 3: Vector Store Indexing")
            print("-" * 80)
            # In full mode, index ALL processed files (not just newly processed ones)
            # This ensures files that were processed but failed indexing are automatically retried
            success, failed = indexer.index_batch(
                max_files=args.max_files,
                filter_sha256=None  # Index all pending, for self-healing behavior
            )
            print(f"\n✅ Index: {success} successful, {failed} failed\n")
        
        print("="*80)
        print("✨ Pipeline complete!")
        print("="*80 + "\n")
        
        # Force clean exit to avoid hanging on background threads/processes
        # Aggressively shutdown any ProcessPoolExecutor instances
        import concurrent.futures.process as proc
        for executor in proc._threads_wakeups:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except:
                pass
        
        # Force immediate exit
        os._exit(0)
    
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print("\nPlease check your .env file. See .env.example for reference.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
