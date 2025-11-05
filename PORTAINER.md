# Portainer Deployment Guide

## 🐳 Using AI Knowledge Base with Portainer

This guide covers deploying and managing the AI Knowledge Base stack in Portainer.

## 📋 Prerequisites

- Portainer installed and running
- Docker environment connected to Portainer
- `.env` file configured with credentials

## 🚀 Initial Deployment

### 1. Deploy Stack in Portainer

**Via UI:**
1. Login to Portainer
2. Navigate to **Stacks** → **Add Stack**
3. Name: `ai-knowledge-base`
4. **Build method**: Choose one:
   - **Upload**: Upload your `docker-compose.yml`
   - **Repository**: Connect to your Git repo
   - **Editor**: Paste docker-compose.yml content

5. **Environment variables**: Add from your `.env` file:
   ```
   # PostgreSQL Database
   POSTGRES_DB=ai_knowledge_base
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=your-secure-password
   POSTGRES_HOST=postgres
   POSTGRES_PORT=5432
   
   # Google Drive
   GOOGLE_SERVICE_ACCOUNT_FILE=./google-service-account.json
   GOOGLE_DRIVE_FOLDER_ID=your-folder-id
   
   # S3 Storage
   S3_ENDPOINT=https://your-s3-endpoint
   S3_ACCESS_KEY=your-access-key
   S3_SECRET_KEY=your-secret-key
   S3_BUCKET=your-bucket-name
   S3_REGION=us-east-1
   
   # OpenAI
   OPENAI_API_KEY=sk-proj-...
   VECTOR_STORE_ID=vs_...
   
   # API
   API_PORT=8000
   ```

6. Click **Deploy the stack**

### 2. Verify Services

After deployment, check:
- ✅ `ai-kb-postgres` - Running
- ✅ `ai-kb-api` - Running  
- ⏸️ `ai-kb-ingest` - Exited (this is normal!)

The ingest service is designed to run on-demand, not continuously.

## 🔄 Running Ingestion Jobs

### Method 1: Duplicate & Run (Easiest)

**For one-time or manual runs:**

1. Go to **Containers**
2. Find `ai-kb-ingest` container (may show as Exited)
3. Click **⋮** (three dots) → **Duplicate/Edit**
4. Scroll to **Command & logging**
5. Change **Command** to:
   ```
   /app/.venv/bin/python main.py full --max-files 100
   ```
6. **Optional**: Change container name to `ai-kb-ingest-job-manual`
7. Click **Deploy the container**
8. View logs: Click container → **Logs** tab

**Common Commands:**
```bash
# Full pipeline (sync + process + index)
/app/.venv/bin/python main.py full --max-files 100

# Sync only
/app/.venv/bin/python main.py sync --max-files 100

# Process only
/app/.venv/bin/python main.py process --max-files 50

# Index only
/app/.venv/bin/python main.py index --max-files 50

# Show statistics
/app/.venv/bin/python main.py stats

# Dry run (test without changes)
/app/.venv/bin/python main.py --dry-run sync --max-files 5
```

### Method 2: Container Webhooks (Scheduled)

**For automated scheduled runs:**

1. **Create a dedicated job container:**
   - Go to **Containers** → **Add container**
   - Name: `ai-kb-ingest-scheduled`
   - Image: `ai-kb-ingest:latest`
   - Command: `/app/.venv/bin/python main.py full --max-files 100`
   
2. **Configure networking:**
   - Network: `ai-kb-network` (or your stack's network)
   
3. **Configure volumes:**
   - Add volume: `ai-knowledge-base_shared_data:/app/data`
   - Add bind: `/path/to/service-account.json:/app/service-account.json:ro`
   
4. **Configure environment:**
   - Copy all environment variables from the ingest service
   
5. **Set restart policy:**
   - Restart policy: **Never** (jobs shouldn't restart)
   
6. **Enable webhook:**
   - Scroll to **Webhooks**
   - Enable webhook
   - Copy the webhook URL
   
7. **Schedule with cron (on host or another server):**
   ```bash
   # Add to crontab
   crontab -e
   
   # Run every 6 hours
   0 */6 * * * curl -X POST https://your-portainer.example.com/api/webhooks/your-webhook-id
   ```

### Method 3: Portainer API (Advanced)

**For programmatic control:**

```bash
#!/bin/bash
# portainer-ingest-job.sh

PORTAINER_URL="https://portainer.example.com"
API_KEY="ptr_your-api-key-here"
ENDPOINT_ID="1"  # Your Docker endpoint ID

# Create and start a new container
curl -X POST "${PORTAINER_URL}/api/endpoints/${ENDPOINT_ID}/docker/containers/create?name=ingest-job-$(date +%s)" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "Image": "ai-kb-ingest:latest",
  "Cmd": ["/app/.venv/bin/python", "main.py", "full", "--max-files", "100"],
  "Env": [
    "DATABASE_PATH=/app/data/pipeline.db",
    "POSTGRES_HOST=postgres",
    "POSTGRES_DB=ai_knowledge_base",
    "POSTGRES_USER=postgres",
    "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}",
    "GOOGLE_SERVICE_ACCOUNT_FILE=/app/service-account.json",
    "OPENAI_API_KEY=${OPENAI_API_KEY}",
    "VECTOR_STORE_ID=${VECTOR_STORE_ID}"
  ],
  "HostConfig": {
    "NetworkMode": "ai-knowledge-base_ai-kb-network",
    "Binds": [
      "ai-knowledge-base_shared_data:/app/data",
      "${PWD}/google-service-account.json:/app/service-account.json:ro"
    ],
    "RestartPolicy": {
      "Name": "no"
    }
  }
}
EOF
```

**Get API Key:**
1. In Portainer: **User** (top right) → **My account**
2. Scroll to **Access tokens**
3. Click **Add access token**
4. Name: `ingest-cron`
5. Copy the token (shown once!)

### Method 4: Portainer Business Edition

If you have **Portainer Business Edition**, use built-in scheduling:

1. Go to **Containers**
2. Select `ai-kb-ingest`
3. Click **Schedule**
4. Configure:
   - Schedule type: **Cron**
   - Cron expression: `0 */6 * * *` (every 6 hours)
   - Command override: `/app/.venv/bin/python main.py full --max-files 100`
5. Save

## 📊 Monitoring

### Via Portainer UI

**Check Container Status:**
1. Go to **Containers**
2. Filter by `ai-kb`
3. View:
   - Status (Running/Exited)
   - Resource usage (CPU, Memory)
   - Last execution time

**View Logs:**
1. Click container name
2. Go to **Logs** tab
3. Enable **Auto-refresh** for live monitoring
4. Use **Search** to filter logs

**Check Stats:**
Run a container with stats command:
1. **Containers** → **Add container**
2. Image: `ai-kb-ingest:latest`
3. Command: `/app/.venv/bin/python main.py stats`
4. Deploy and check logs

### Via API

**Check API Health:**
```bash
curl http://your-server:8000/health
```

**Check Database:**
Access PostgreSQL via Portainer:
1. Go to **Containers** → `ai-kb-postgres`
2. Click **Console** → **Connect**
3. Run:
   ```sql
   \c ai_knowledge_base
   SELECT status, COUNT(*) FROM file_state GROUP BY status;
   ```

## 🔧 Maintenance

### Update Services

**Update images:**
1. Go to **Stacks** → `ai-knowledge-base`
2. Click **Editor**
3. No changes needed if using local build
4. Click **Update the stack**
5. Check **Pull latest image** if using registry
6. Apply changes

**Rebuild after code changes:**
```bash
# On your development machine
docker-compose build
docker tag ai-kb-ingest:latest your-registry/ai-kb-ingest:latest
docker push your-registry/ai-kb-ingest:latest

# In Portainer
1. Update stack with new image tag
2. Click "Pull and redeploy"
```

### View Volumes

1. Go to **Volumes**
2. Find:
   - `ai-knowledge-base_postgres_data` - Database
   - `ai-knowledge-base_shared_data` - SQLite & temp files
3. Click **Browse** to inspect files

### Backup Database

**Via Portainer:**
1. **Containers** → `ai-kb-postgres` → **Console**
2. Connect and run:
   ```bash
   pg_dump -U postgres ai_knowledge_base > /tmp/backup.sql
   ```
3. Use **Volumes** → Browse to download

**Automated:**
Create a backup container in your stack:
```yaml
backup:
  image: postgres:16-alpine
  command: >
    sh -c "pg_dump -h postgres -U postgres ai_knowledge_base > /backup/ai-kb-$(date +%Y%m%d).sql"
  environment:
    PGPASSWORD: ${POSTGRES_PASSWORD}
  volumes:
    - ./backups:/backup
  networks:
    - ai-kb-network
  profiles:
    - backup
```

Run via Portainer when needed.

## 🐛 Troubleshooting

### Ingest Job Fails

1. **Check logs:**
   - Portainer → Containers → `ai-kb-ingest` → Logs
   - Look for error messages

2. **Common issues:**
   - **Service account not found**: Check volume mount
   - **S3 connection failed**: Verify S3 credentials
   - **OpenAI API error**: Check API key and Vector Store ID
   - **Database locked**: Ensure no other job is running

3. **Test with dry run:**
   ```
   /app/.venv/bin/python main.py --dry-run sync --max-files 5
   ```

### API Not Responding

1. **Check container status:**
   - Should show as "Running"
   - Check health: Green = healthy

2. **View logs:**
   - Look for startup errors
   - Check port binding

3. **Restart:**
   - Containers → `ai-kb-api` → **Restart**

### Database Issues

1. **Check PostgreSQL health:**
   ```bash
   docker exec ai-kb-postgres pg_isready -U postgres
   ```

2. **View logs:**
   - Check for disk space issues
   - Look for connection errors

## 📋 Recommended Schedule

**For production:**

| Time | Command | Purpose |
|------|---------|---------|
| Every 6 hours | `full --max-files 100` | Regular sync |
| Daily 9 AM | `stats` | Review statistics |
| Weekly Sun 2 AM | `cleanup` | Clean stale files |

**Setup cron on host:**
```bash
# Every 6 hours - full pipeline
0 */6 * * * curl -X POST https://portainer.example.com/api/webhooks/xxx

# Daily at 9 AM - check stats (send to email/Slack)
0 9 * * * docker exec ai-kb-ingest python main.py stats | mail -s "AI KB Stats" admin@example.com

# Weekly Sunday 2 AM - cleanup
0 2 * * 0 curl -X POST https://portainer.example.com/api/webhooks/yyy
```

## 🎯 Best Practices

1. **Don't run ingest continuously** - It's a batch job, not a service
2. **Monitor first few runs** - Check logs to ensure success
3. **Start with small batches** - Use `--max-files 10` initially
4. **Scale gradually** - Increase to 100-500 based on volume
5. **Set up alerts** - Use webhooks to notify on failures
6. **Regular cleanup** - Run cleanup command weekly
7. **Backup database** - Weekly or before major changes

## 🚀 Quick Start Summary

1. **Deploy stack in Portainer** with docker-compose.yml
2. **Verify services** - API and PostgreSQL should be running
3. **Run first ingestion**:
   - Containers → Duplicate `ai-kb-ingest`
   - Command: `/app/.venv/bin/python main.py sync --max-files 10`
   - Deploy and check logs
4. **Set up scheduled runs** using webhooks + cron
5. **Monitor** via Portainer UI

Need help? Check the main README.md or container logs!
