"""
AI Knowledge Base Ingest Pipeline
Main entry point for the document ingestion workflow
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
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
        choices=["sync", "process", "index", "full"],
        default="full",
        help="Command to run: sync (Drive→S3), process (S3→Unstructured), index (→Vector Store), full (all). Default: full"
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
        "--use-processes",
        action="store_true",
        help="Use ProcessPoolExecutor for CPU-bound tasks (better for OCR-heavy workloads)"
    )
    
    args = parser.parse_args()
    
    try:
        # Apply max_files from CLI (already has correct default from config)
        config.max_files_per_run = args.max_files
        
        # Initialize components
        drive_sync = DriveSync(config, dry_run=args.dry_run)
        processor = UnstructuredProcessor(config, dry_run=args.dry_run, use_processes=args.use_processes)
        indexer = VectorStoreIndexer(config, dry_run=args.dry_run)
        
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
                max_files=config.max_files_per_run,
                force_full=args.force_full_sync
            )
            print(f"\n✅ Sync: {success} successful, {failed} failed\n")
        else:
            synced_hashes = []
        
        if args.command == "process" or args.command == "full":
            print("\n🔄 STAGE 2: Unstructured Processing")
            print("-" * 80)
            # In full mode, only process files that were just synced
            filter_hashes = synced_hashes if args.command == "full" else None
            success, failed, processed_hashes = processor.process_batch(
                max_files=config.max_files_per_run,
                retry_failed=args.retry_failed,
                filter_sha256=filter_hashes
            )
            print(f"\n✅ Process: {success} successful, {failed} failed\n")
        else:
            processed_hashes = []
        
        if args.command == "index" or args.command == "full":
            print("\n📚 STAGE 3: Vector Store Indexing")
            print("-" * 80)
            # In full mode, only index files that were just processed
            filter_hashes = processed_hashes if args.command == "full" else None
            success, failed = indexer.index_batch(
                max_files=config.max_files_per_run,
                filter_sha256=filter_hashes
            )
            print(f"\n✅ Index: {success} successful, {failed} failed\n")
        
        print("="*80)
        print("✨ Pipeline complete!")
        print("="*80 + "\n")
    
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
