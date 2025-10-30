# Summary: Memory Leak Fix & Migration Plan

## What Was Wrong

**Memory Leak in processor.py:**
- `future_to_key` dictionary held ALL file processing futures in memory simultaneously
- When processing 2,843 files, all results accumulated causing OOM (exit code 137)
- No cleanup between batches
- MacBook M4 with Docker couldn't handle the load

## What Was Fixed

### 1. Chunked Processing (`process_batch_chunked()`)
- **Location:** `services/ingest/src/processor.py` line 940+
- **How it works:**
  - Processes files in chunks of 100 (configurable)
  - Explicit `gc.collect()` between chunks to free memory
  - Progress tracking per chunk and overall
  - Same parallel processing capabilities as original
  
### 2. Updated main.py
- **Lines changed:** 243, 257
- **Change:** `process_batch()` → `process_batch_chunked(chunk_size=100)`
- **Impact:** Cleanup command now uses memory-efficient processing

### 3. Other Fixes Included
- **__str__ bug fix:** Lines 482, 518 with None-safety checks
- **EPUB support:** Added to `pyproject.toml`
- **Helper scripts:** `check_errors.py`, `reset_stuck_files.py`

## Current Status

**Database State:**
- Total files: 3,275
- Indexed: 432
- Processed: 105
- Synced: 2,669
- Failed: 61
- Processing: 23 (stuck, will cleanup on next run)

**Ready for:**
✅ Migration to PC (128GB RAM + GPU)
✅ Large-scale processing with chunked batches
✅ Better error handling and recovery

## Next Steps

### Option A: Continue on MacBook (Slow)
```bash
# Rebuild Docker image with fixes
docker compose build ingest

# Process in small chunks
docker compose run --rm ingest python main.py cleanup --auto-fix

# This will use chunked processing automatically
# Expected time: 12-24 hours for remaining 2,669 files
```

### Option B: Migrate to PC (Recommended)
Follow `MIGRATION_PLAN.md`:

1. **Export data from MacBook:**
```bash
# Database backup
docker compose exec postgres pg_dump -U postgres -d ai_knowledge_base -F c -f /tmp/backup.dump
docker compose cp postgres:/tmp/backup.dump ./backup.dump

# S3/MinIO backup
docker run --rm -v ai-kb-minio-data:/data -v $(pwd):/backup alpine tar czf /backup/s3-data.tar.gz /data
```

2. **Transfer to PC:**
```bash
# From MacBook
rsync -avz --progress \
    --exclude 'services/*/src/__pycache__' \
    ~/DEV/ai-knowledge-base-ingest/ \
    user@pc-ip:~/ai-knowledge-base-ingest/
```

3. **Setup on PC:**
```bash
# On PC
cd ~/ai-knowledge-base-ingest
docker compose up -d postgres minio
docker compose cp backup.dump postgres:/tmp/
docker compose exec postgres pg_restore -U postgres -d ai_knowledge_base /tmp/backup.dump

# Restore S3
docker run --rm -v ai-kb-minio-data:/data -v $(pwd):/backup alpine tar xzf /backup/s3-data.tar.gz -C /

# Build and test
docker compose build
docker compose run --rm ingest python main.py process --max-files 10
```

4. **Run full pipeline:**
```bash
# With chunked processing, this should work smoothly
docker compose run --rm ingest python main.py cleanup --auto-fix

# Or run specific stages
docker compose run --rm ingest python main.py process --max-files 1000
docker compose run --rm ingest python main.py index
```

## Performance Comparison

| Environment | Speed | Memory | Batch Size | Total Time (3,275 files) |
|------------|-------|--------|------------|--------------------------|
| MacBook M4 | 67 s/file | 8-16GB | 100 | 12-24 hours |
| PC (128GB+GPU) | 10-30 s/file* | 128GB | 500+ | 2-6 hours* |

*Estimated based on native Docker performance and more RAM

## Key Files Changed

1. **services/ingest/src/processor.py**
   - Added `process_batch_chunked()` method
   - Added `_process_chunk()` helper
   - Fixed __str__ bug at lines 482, 518

2. **services/ingest/main.py**
   - Updated cleanup command to use chunked processing

3. **services/ingest/pyproject.toml**
   - Added `epub` extra to unstructured dependency

4. **MIGRATION_PLAN.md** (NEW)
   - Complete guide for MacBook → PC migration
   - Backup/restore procedures
   - Performance expectations
   - Rollback plan

5. **check_errors.py** (NEW)
   - Helper script to analyze error patterns

6. **reset_stuck_files.py** (NEW)
   - Helper script to reset OOM crashed files

## Git Commit

```
feat: Add chunked processing to fix memory leaks and OOM issues
Commit: 2118229
```

All changes are committed and ready for migration!
