# PC Migration Checklist

Use this checklist when migrating from MacBook to PC.

## Pre-Migration (MacBook)

- [ ] **Commit all code changes**
  ```bash
  git push origin main
  ```

- [ ] **Export PostgreSQL database**
  ```bash
  docker compose exec postgres pg_dump -U postgres -d ai_knowledge_base -F c -f /tmp/backup.dump
  docker compose cp postgres:/tmp/backup.dump ./backup.dump
  ls -lh backup.dump  # Verify file created
  ```

- [ ] **Export MinIO/S3 data**
  ```bash
  docker run --rm -v ai-kb-minio-data:/data -v $(pwd):/backup alpine tar czf /backup/s3-data.tar.gz /data
  ls -lh s3-data.tar.gz  # Verify file created (should be several GB)
  ```

- [ ] **Backup configuration files**
  ```bash
  cp .env .env.macbook.backup
  cp services/ingest/.env services/ingest/.env.macbook.backup
  cp somer-services-458421-ee757e0c4238.json credentials.json.backup
  ```

- [ ] **Verify backups before proceeding**
  ```bash
  ls -lh backup.dump s3-data.tar.gz *.backup
  ```

## PC Setup

- [ ] **Install Docker on PC**
  ```bash
  sudo apt update
  sudo apt install docker.io docker-compose git
  sudo systemctl start docker
  sudo systemctl enable docker
  sudo usermod -aG docker $USER
  # Log out and back in for group changes
  ```

- [ ] **Clone repository**
  ```bash
  git clone https://github.com/hasomerhacairhu/ai-knowledge-base-ingest.git
  cd ai-knowledge-base-ingest
  ```

- [ ] **Transfer files from MacBook** (choose one method):
  
  **Method A: rsync (recommended)**
  ```bash
  # Run from MacBook
  rsync -avz --progress \
      --exclude '.git' \
      --exclude 'services/*/src/__pycache__' \
      ~/DEV/ai-knowledge-base-ingest/ \
      user@pc-ip:~/ai-knowledge-base-ingest/
  ```
  
  **Method B: scp individual files**
  ```bash
  # Run from MacBook
  scp backup.dump user@pc-ip:~/ai-knowledge-base-ingest/
  scp s3-data.tar.gz user@pc-ip:~/ai-knowledge-base-ingest/
  scp .env.macbook.backup user@pc-ip:~/ai-knowledge-base-ingest/.env
  scp services/ingest/.env.macbook.backup user@pc-ip:~/ai-knowledge-base-ingest/services/ingest/.env
  scp somer-services-458421-ee757e0c4238.json user@pc-ip:~/ai-knowledge-base-ingest/
  ```

- [ ] **Verify files on PC**
  ```bash
  ls -lh backup.dump s3-data.tar.gz
  ls -lh .env services/ingest/.env somer-services-458421-ee757e0c4238.json
  ```

## Data Restoration

- [ ] **Start PostgreSQL**
  ```bash
  docker compose up -d postgres
  sleep 5  # Wait for startup
  docker compose ps  # Verify postgres is running
  ```

- [ ] **Restore database**
  ```bash
  docker compose cp backup.dump postgres:/tmp/
  docker compose exec postgres pg_restore -U postgres -d ai_knowledge_base -c /tmp/backup.dump
  # Note: -c flag drops existing objects (clean restore)
  ```

- [ ] **Verify database**
  ```bash
  docker compose exec postgres psql -U postgres -d ai_knowledge_base -c "SELECT COUNT(*) FROM file_state;"
  # Should show 3,275 (or whatever your count was)
  
  docker compose exec postgres psql -U postgres -d ai_knowledge_base -c "SELECT status, COUNT(*) FROM file_state GROUP BY status ORDER BY status;"
  # Should match MacBook status distribution
  ```

- [ ] **Start MinIO**
  ```bash
  docker compose up -d minio
  sleep 3
  docker compose ps  # Verify minio is running
  ```

- [ ] **Restore S3 data**
  ```bash
  # Extract backup to MinIO volume
  docker run --rm -v ai-kb-minio-data:/data -v $(pwd):/backup alpine tar xzf /backup/s3-data.tar.gz -C /
  
  # Verify data
  docker compose exec minio ls /data/ai-knowledge-base/objects/ | head -20
  ```

- [ ] **Configure MinIO access (optional, for manual checking)**
  ```bash
  docker compose exec minio mc alias set local http://localhost:9000 minioadmin minioadmin
  docker compose exec minio mc ls local/ai-knowledge-base/
  ```

## Build & Test

- [ ] **Build Docker images**
  ```bash
  docker compose build --no-cache
  # This will take 5-10 minutes (includes Tesseract OCR, Python packages)
  ```

- [ ] **Test with 1 file**
  ```bash
  docker compose run --rm ingest python main.py process --max-files 1
  # Should complete successfully
  ```

- [ ] **Test with 10 files**
  ```bash
  docker compose run --rm ingest python main.py process --max-files 10
  # Verify chunked processing works
  ```

- [ ] **Check database after test**
  ```bash
  docker compose exec postgres psql -U postgres -d ai_knowledge_base -c "SELECT status, COUNT(*) FROM file_state GROUP BY status ORDER BY status;"
  # Should see ~10 more processed files
  ```

## GPU Configuration (Optional)

- [ ] **Check GPU availability**
  ```bash
  nvidia-smi
  # Should show GPU info if NVIDIA driver installed
  ```

- [ ] **Install NVIDIA Docker runtime**
  ```bash
  distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
  curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
  curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
  sudo apt-get update && sudo apt-get install -y nvidia-docker2
  sudo systemctl restart docker
  ```

- [ ] **Test GPU in Docker**
  ```bash
  docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
  # Should show GPU info from inside container
  ```

- [ ] **Update docker-compose.yml for GPU** (if needed)
  ```yaml
  services:
    ingest:
      deploy:
        resources:
          reservations:
            devices:
              - driver: nvidia
                count: 1
                capabilities: [gpu]
  ```

## Full Production Run

- [ ] **Start full pipeline (background)**
  ```bash
  docker compose up -d ingest
  ```

- [ ] **Monitor logs**
  ```bash
  docker compose logs -f ingest
  ```

- [ ] **Monitor progress** (in another terminal)
  ```bash
  watch -n 30 'docker compose exec postgres psql -U postgres -d ai_knowledge_base -c "SELECT status, COUNT(*) FROM file_state GROUP BY status ORDER BY status;"'
  ```

- [ ] **Monitor system resources**
  ```bash
  docker stats
  # or
  htop
  ```

## Verification

- [ ] **Check final counts**
  ```bash
  docker compose exec postgres psql -U postgres -d ai_knowledge_base -c "
  SELECT 
    status, 
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as percentage
  FROM file_state 
  GROUP BY status 
  ORDER BY status;"
  ```

- [ ] **Check for errors**
  ```bash
  docker compose run --rm ingest python check_errors.py
  ```

- [ ] **Test API (if running)**
  ```bash
  curl http://localhost:8000/health
  curl http://localhost:8000/search?query=test
  ```

- [ ] **Verify OpenAI Vector Store**
  - Log into OpenAI platform
  - Check vector store `vs_6900e6fc7c94819187c6ec114fd3adc9`
  - Verify file count matches indexed count

## Post-Migration

- [ ] **Document actual performance**
  - Record processing speed (seconds/file)
  - Record total time for full batch
  - Record memory usage patterns

- [ ] **Clean up MacBook** (after 1 week of stable operation)
  ```bash
  # On MacBook
  docker compose down -v  # Remove all containers and volumes
  rm backup.dump s3-data.tar.gz
  # Optionally delete local repo if pushing to git
  ```

- [ ] **Update documentation**
  - Add actual performance numbers to MIGRATION_PLAN.md
  - Document any PC-specific configuration changes

- [ ] **Schedule regular backups on PC**
  ```bash
  # Add to crontab for daily database backup
  0 2 * * * cd ~/ai-knowledge-base-ingest && docker compose exec postgres pg_dump -U postgres -d ai_knowledge_base -F c -f /tmp/daily_backup.dump
  ```

## Troubleshooting

### Database restore fails
```bash
# Try without -c flag (don't drop existing)
docker compose exec postgres pg_restore -U postgres -d ai_knowledge_base /tmp/backup.dump

# Or recreate database from scratch
docker compose exec postgres psql -U postgres -c "DROP DATABASE ai_knowledge_base;"
docker compose exec postgres psql -U postgres -c "CREATE DATABASE ai_knowledge_base;"
docker compose exec postgres pg_restore -U postgres -d ai_knowledge_base /tmp/backup.dump
```

### MinIO data missing
```bash
# Check volume
docker volume ls | grep minio
docker volume inspect ai-kb-minio-data

# Verify backup extraction
docker run --rm -v ai-kb-minio-data:/data alpine ls -lh /data/
```

### Processing fails
```bash
# Check logs
docker compose logs ingest

# Check environment variables
docker compose run --rm ingest env | grep -E '(OPENAI|GOOGLE|POSTGRES|S3)'

# Test database connection
docker compose run --rm ingest python -c "from src.database import DatabaseManager; db = DatabaseManager(); print('OK')"

# Test S3 connection
docker compose run --rm ingest python -c "from src.utils import S3Manager; from src.config import Config; s3 = S3Manager(Config()); print(s3.list_objects('objects/')[:5])"
```

### Out of memory on PC
```bash
# Reduce chunk size in main.py
# Change chunk_size=100 to chunk_size=50

# Or reduce workers in .env
MAX_WORKERS=3  # Instead of 5

# Or disable parallel processing
docker compose run --rm ingest python main.py process --no-parallel
```

---

**Estimated Total Migration Time:** 2-4 hours (depending on data transfer speed)

**Estimated Processing Time on PC:** 2-6 hours for remaining ~2,600 files
