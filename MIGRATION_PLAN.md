# Migration Plan: MacBook M4 → PC (128GB RAM + GPU)

## Current Issues on MacBook

### 1. **Memory Leak in processor.py**
**Problem:** `future_to_key` dictionary holds ALL futures/results in memory simultaneously
- Line 862-877: Submits ALL files at once
- Line 890-905: Results accumulate, no cleanup until batch complete
- Causes OOM when processing 2,843 files

**Fix:** Process in chunks with explicit cleanup between batches

### 2. **Slow Processing**
**Problem:** M4 MacBook running Docker is slow for CPU/OCR intensive work
- Average: 67 seconds per file
- OCR uses CPU heavily (no GPU acceleration)
- Docker on macOS has performance overhead

**Solution:** PC with GPU can leverage:
- GPU acceleration for OCR (if Tesseract/Unstructured supports it)
- Native Docker performance (Linux)
- 128GB RAM allows larger batches

### 3. **No Batch Chunking Strategy**
**Problem:** Process tries to handle all files at once
- No memory cleanup between chunks
- Progress lost on crash
- No incremental save points

**Fix:** Implement chunked batch processing (100-200 files per chunk)

---

## Pre-Migration Fixes Required

### Fix 1: Implement Chunked Processing

**File:** `services/ingest/src/processor.py`

Add after line 850:
```python
def process_batch_chunked(self, max_files: Optional[int] = None, chunk_size: int = 100, 
                         parallel: bool = True, retry_failed: bool = False) -> Tuple[int, int, List[str]]:
    """
    Process files in chunks to avoid memory buildup.
    
    Args:
        max_files: Total files to process
        chunk_size: Files per chunk (default: 100)
        parallel: Use parallel processing
        retry_failed: Retry previously failed files
    
    Returns:
        Tuple of (total_successful, total_failed, all_processed_sha256s)
    """
    import gc
    
    # Get all files to process
    files = self.list_incoming_files(max_files=max_files, retry_failed=retry_failed)
    
    if not files:
        logger.info("✨ No files to process")
        return 0, 0, []
    
    total_successful = 0
    total_failed = 0
    all_processed_sha256s = []
    
    # Process in chunks
    for i in range(0, len(files), chunk_size):
        chunk = files[i:i + chunk_size]
        chunk_num = (i // chunk_size) + 1
        total_chunks = (len(files) + chunk_size - 1) // chunk_size
        
        logger.info(f"\n{'='*80}")
        logger.info(f"📦 Processing Chunk {chunk_num}/{total_chunks} ({len(chunk)} files)")
        logger.info(f"{'='*80}")
        
        # Process this chunk
        success, failed, sha256s = self._process_chunk(chunk, parallel)
        
        total_successful += success
        total_failed += failed
        all_processed_sha256s.extend(sha256s)
        
        # Explicit cleanup between chunks
        gc.collect()
        
        logger.info(f"✅ Chunk {chunk_num} complete: {success} success, {failed} failed")
        logger.info(f"📊 Overall progress: {total_successful}/{len(files)} ({100*total_successful/len(files):.1f}%)")
    
    return total_successful, total_failed, all_processed_sha256s

def _process_chunk(self, files: List[Tuple[str, str]], parallel: bool) -> Tuple[int, int, List[str]]:
    """Process a single chunk of files."""
    tracker = ProgressTracker(len(files), "Processing")
    processed_sha256_hashes = []
    
    if parallel and self.max_workers > 1:
        ExecutorClass = ProcessPoolExecutor if self.use_processes else ThreadPoolExecutor
        self.quiet_mode = True
        
        with ExecutorClass(max_workers=self.max_workers) as executor:
            if self.use_processes:
                db_config = {
                    "host": self.database.connection_params["host"],
                    "port": self.database.connection_params["port"],
                    "database": self.database.connection_params["database"],
                    "user": self.database.connection_params["user"],
                    "password": self.database.connection_params["password"]
                }
                future_to_key = {
                    executor.submit(_process_file_worker, sha256, s3_key, self.config, db_config, self.dry_run, self.quiet_mode): (s3_key, sha256)
                    for s3_key, sha256 in files
                }
            else:
                future_to_key = {
                    executor.submit(self.process_file, s3_key, sha256): (s3_key, sha256)
                    for s3_key, sha256 in files
                }
            
            with tqdm(total=len(files), desc="🔄 Processing chunk", unit="file", 
                      leave=False, dynamic_ncols=True) as pbar:
                for future in as_completed(future_to_key):
                    s3_key, sha256 = future_to_key[future]
                    try:
                        result_sha256 = future.result()
                        tracker.update(success=bool(result_sha256))
                        if result_sha256:
                            processed_sha256_hashes.append(result_sha256)
                    except Exception as e:
                        tracker.update(success=False)
                    
                    pbar.set_postfix_str(f"✅ {tracker.successful} | ❌ {tracker.failed}")
                    pbar.update(1)
        
        self.quiet_mode = False
    else:
        # Sequential processing
        with tqdm(total=len(files), desc="🔄 Processing chunk", unit="file", leave=False) as pbar:
            for s3_key, sha256 in files:
                result_sha256 = self.process_file(s3_key, sha256)
                tracker.update(success=bool(result_sha256))
                if result_sha256:
                    processed_sha256_hashes.append(result_sha256)
                pbar.set_postfix_str(f"✅ {tracker.successful} | ❌ {tracker.failed}")
                pbar.update(1)
    
    return tracker.successful, tracker.failed, processed_sha256_hashes
```

### Fix 2: Update main.py to use chunked processing

**File:** `services/ingest/main.py`

Replace `process_batch()` calls with `process_batch_chunked()`:
- Line 243: Add `chunk_size=100`
- Line 257: Add `chunk_size=100`

### Fix 3: Add memory monitoring

**File:** `services/ingest/src/processor.py`

Add at top:
```python
import psutil
import gc

def log_memory_usage():
    """Log current memory usage."""
    process = psutil.Process()
    mem_info = process.memory_info()
    mem_mb = mem_info.rss / 1024 / 1024
    logger.info(f"💾 Memory usage: {mem_mb:.1f} MB")
```

Call after each chunk in `process_batch_chunked()`.

---

## Migration Steps: MacBook → PC

### Phase 1: Backup Current State

1. **Export PostgreSQL Database**
```bash
# On MacBook
docker compose exec postgres pg_dump -U postgres -d ai_knowledge_base -F c -f /tmp/backup.dump
docker compose cp postgres:/tmp/backup.dump ./backup.dump
```

2. **Export MinIO/S3 Data**
```bash
# Check total size first
docker compose exec minio du -sh /data

# Export using mc (minio client)
docker compose exec minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker compose exec minio mc mirror local/ai-knowledge-base /tmp/s3-backup

# Or use docker volume backup
docker run --rm -v ai-kb-minio-data:/data -v $(pwd):/backup alpine tar czf /backup/s3-data.tar.gz /data
```

3. **Backup Configuration**
```bash
# Copy all config files
cp .env .env.backup
cp services/ingest/.env services/ingest/.env.backup
cp docker-compose.yml docker-compose.yml.backup
```

### Phase 2: Setup PC Environment

1. **Install Dependencies on PC**
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install docker.io docker-compose git

# Start Docker
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER  # Add user to docker group
```

2. **Clone Repository on PC**
```bash
git clone https://github.com/hasomerhacairhu/ai-knowledge-base-ingest.git
cd ai-knowledge-base-ingest
```

3. **Copy Files from MacBook to PC**
```bash
# On MacBook, rsync to PC
rsync -avz --progress \
    --exclude 'services/*/src/__pycache__' \
    --exclude '.git' \
    ~/DEV/ai-knowledge-base-ingest/ \
    user@pc-ip:~/ai-knowledge-base-ingest/

# Or use SCP for specific files
scp backup.dump user@pc-ip:~/ai-knowledge-base-ingest/
scp s3-data.tar.gz user@pc-ip:~/ai-knowledge-base-ingest/
```

4. **Update Configuration on PC**
```bash
# Edit .env files
nano services/ingest/.env

# Update Google Drive credentials path if needed
# Update OpenAI API key
# Set MAX_FILES_PER_RUN based on PC specs (e.g., 500)
```

### Phase 3: Restore Data on PC

1. **Start PostgreSQL**
```bash
cd ~/ai-knowledge-base-ingest
docker compose up -d postgres
```

2. **Restore Database**
```bash
# Copy dump into container
docker compose cp backup.dump postgres:/tmp/

# Restore
docker compose exec postgres pg_restore -U postgres -d ai_knowledge_base /tmp/backup.dump
```

3. **Restore S3/MinIO Data**
```bash
# Start MinIO
docker compose up -d minio

# Restore data
docker run --rm -v ai-kb-minio-data:/data -v $(pwd):/backup alpine tar xzf /backup/s3-data.tar.gz -C /
```

4. **Verify Data**
```bash
# Check database
docker compose exec postgres psql -U postgres -d ai_knowledge_base -c "SELECT COUNT(*) FROM file_state;"

# Check S3
docker compose exec minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker compose exec minio mc ls local/ai-knowledge-base/objects/ | wc -l
```

### Phase 4: Build and Test on PC

1. **Build Docker Images**
```bash
docker compose build --no-cache
```

2. **Test with Small Batch**
```bash
# Process 10 files to verify everything works
docker compose run --rm ingest python main.py process --max-files 10
```

3. **Verify GPU Access (if applicable)**
```bash
# Check if NVIDIA GPU is available
nvidia-smi

# Add GPU support to docker-compose.yml if needed:
# services:
#   ingest:
#     deploy:
#       resources:
#         reservations:
#           devices:
#             - driver: nvidia
#               count: 1
#               capabilities: [gpu]
```

### Phase 5: Full Migration

1. **Stop MacBook Services**
```bash
# On MacBook
docker compose down
```

2. **Run Full Pipeline on PC**
```bash
# On PC
docker compose run --rm ingest python main.py full --max-files 10000

# Or run in background
docker compose up -d ingest
docker compose logs -f ingest
```

3. **Monitor Progress**
```bash
# Check database status
docker compose exec postgres psql -U postgres -d ai_knowledge_base -c "
SELECT status, COUNT(*) 
FROM file_state 
GROUP BY status 
ORDER BY status;
"

# Monitor memory
docker stats

# Check logs
docker compose logs -f ingest
```

---

## Performance Expectations

### MacBook M4 (Current)
- **Processing Speed:** ~67 seconds/file
- **Memory:** 8-16GB (OOM at 2,843 files)
- **Batch Size:** 100-200 files max
- **Total Time:** ~12-24 hours for 3,275 files

### PC (128GB RAM + GPU)
- **Processing Speed:** ~10-30 seconds/file (estimated)
- **Memory:** Can handle 500-1000 files per batch
- **Batch Size:** 500 files per chunk
- **Total Time:** ~2-6 hours for 3,275 files (estimated)

---

## Rollback Plan

If migration fails:

1. **Keep MacBook backup intact** - don't delete until PC is verified
2. **Database rollback**: Re-import `backup.dump` on MacBook
3. **S3 rollback**: Keep original MinIO volume on MacBook
4. **Continue on MacBook**: Use chunked processing with smaller batches

---

## Post-Migration Checklist

- [ ] All files synced from Google Drive
- [ ] Database restored with correct counts
- [ ] S3/MinIO has all objects and derivatives
- [ ] Test processing 10 files successfully
- [ ] Test indexing to OpenAI Vector Store
- [ ] Verify API endpoints work
- [ ] Run full pipeline end-to-end
- [ ] Monitor for memory leaks
- [ ] Commit all changes to git
- [ ] Delete MacBook backup after 1 week of stable operation

---

## Emergency Contacts

- Google Drive API: Check quotas at https://console.cloud.google.com
- OpenAI API: Check usage at https://platform.openai.com/usage
- GitHub Repo: https://github.com/hasomerhacairhu/ai-knowledge-base-ingest
