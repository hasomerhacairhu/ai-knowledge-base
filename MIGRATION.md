# PostgreSQL Migration Complete ✅

## Summary

Successfully migrated the AI Knowledge Base ingest service from SQLite to PostgreSQL.

## Changes Made

### 1. **Dependencies** (`services/ingest/pyproject.toml`)
- ✅ Added `psycopg2-binary>=2.9.10` for PostgreSQL connectivity
- ✅ Installed via `uv sync` (151 total packages)

### 2. **Configuration** (`services/ingest/src/config.py`)
- ✅ Replaced `database_path: str` with PostgreSQL connection parameters:
  - `postgres_host: str` (default: "localhost")
  - `postgres_port: int` (default: 5432)
  - `postgres_db: str` (default: "ai_knowledge_base")
  - `postgres_user: str` (default: "postgres")
  - `postgres_password: str` (default: "postgres")
- ✅ Reads from environment variables: `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`

### 3. **Database Layer** (`services/ingest/src/database.py`)
- ✅ **Backed up original**: `database.py.sqlite-backup`
- ✅ **Replaced `sqlite3` with `psycopg2`**:
  - Connection pooling with context manager
  - PostgreSQL-specific SQL syntax (`%s` placeholders instead of `?`)
  - Proper `RealDictCursor` for dict-like row access
  - `TIMESTAMP` instead of `TEXT` for datetime fields
  - `NOW()` and `INTERVAL` for date arithmetic
  - `ON CONFLICT` upserts (same as SQLite)
  
### 4. **Database Initialization**
- ✅ Schema auto-created by `Database._init_schema()` on first connection
- ✅ Created `init_db.sql` for reference and manual migration

### 5. **Main Entry Point** (`services/ingest/main.py`)
- ✅ Updated `Database()` instantiation to use new PostgreSQL connection parameters

### 6. **Processor Worker** (`services/ingest/src/processor.py`)
- ✅ Updated `_process_file_worker()` to accept `db_config: dict` instead of `db_path: str`
- ✅ Worker now creates PostgreSQL connections using connection parameters
- ✅ Updated executor to pass `db_config` dict for `ProcessPoolExecutor`

### 7. **Docker Compose** (`docker-compose.yml`)
- ✅ **Fixed corruption** - recreated clean file
- ✅ **PostgreSQL service** (postgres:16-alpine):
  - Persistent volume: `postgres_data`
  - Port: 5432
  - Health checks: `pg_isready`
  - Always running: `restart: unless-stopped`
  
- ✅ **Updated ingest service**:
  - Added PostgreSQL environment variables
  - Depends on healthy postgres
  - Removed SQLite volume mount
  - Portainer-ready labels

- ✅ **Updated API service**:
  - Added PostgreSQL environment variables
  - Depends on healthy postgres

## SQL Differences Handled

| SQLite | PostgreSQL | Status |
|--------|------------|--------|
| `?` placeholders | `%s` placeholders | ✅ |
| `TEXT` for dates | `TIMESTAMP` | ✅ |
| `datetime('now')` | `NOW()` | ✅ |
| `datetime('now', '-24 hours')` | `NOW() - INTERVAL '24 hours'` | ✅ |
| `INSERT OR REPLACE` | `INSERT ... ON CONFLICT` | ✅ (already used) |
| `sqlite3.Row` | `psycopg2.extras.RealDictCursor` | ✅ |
| Single file WAL mode | Connection pooling | ✅ |

## Environment Variables Required

Add to your `.env` file:

```bash
# PostgreSQL Configuration
POSTGRES_HOST=postgres        # or localhost for local dev
POSTGRES_PORT=5432
POSTGRES_DB=ai_knowledge_base
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-secure-password-here
```

## Testing the Migration

### 1. Start PostgreSQL
```bash
docker-compose up -d postgres
```

### 2. Wait for health check
```bash
docker-compose ps postgres
# Should show "healthy" status
```

### 3. Test connection
```bash
docker exec -it ai-kb-postgres psql -U postgres -d ai_knowledge_base -c "\dt"
# Should show: file_state, drive_file_mapping, checkpoint tables
```

### 4. Run ingestion
```bash
cd services/ingest
uv run python main.py stats
# Should connect to PostgreSQL and show statistics
```

### 5. Full pipeline test
```bash
uv run python main.py sync --max-files 5
```

## Migration Strategy (if you have existing SQLite data)

### Option 1: Fresh Start
- Just start using PostgreSQL
- Old SQLite data remains in `/app/data/pipeline.db` for reference
- New syncs will populate PostgreSQL

### Option 2: Migrate Existing Data
```bash
# 1. Export from SQLite
sqlite3 /app/data/pipeline.db << EOF
.headers on
.mode csv
.output file_state.csv
SELECT * FROM file_state;
.output drive_file_mapping.csv
SELECT * FROM drive_file_mapping;
.output checkpoint.csv
SELECT * FROM checkpoint;
EOF

# 2. Import to PostgreSQL
docker exec -i ai-kb-postgres psql -U postgres -d ai_knowledge_base << EOF
COPY file_state FROM '/tmp/file_state.csv' CSV HEADER;
COPY drive_file_mapping FROM '/tmp/drive_file_mapping.csv' CSV HEADER;
COPY checkpoint FROM '/tmp/checkpoint.csv' CSV HEADER;
EOF
```

### Option 3: Use Existing Migrate Command
```bash
# The database.py still has migrate_from_s3_markers() method
# This scans S3 and rebuilds database state from objects/, derivatives/, indexed/
uv run python main.py migrate
```

## Benefits of PostgreSQL

1. ✅ **Better concurrency** - Multiple processes can read/write simultaneously
2. ✅ **Shared database** - API and ingest services share same PostgreSQL instance
3. ✅ **Better reliability** - ACID transactions, proven at scale
4. ✅ **Better tooling** - pgAdmin, DataGrip, psql for debugging
5. ✅ **Better monitoring** - Query logs, slow query analysis, connection stats
6. ✅ **Better backups** - `pg_dump`, point-in-time recovery, WAL archiving
7. ✅ **Better schema evolution** - Migrations with Alembic/Flyway
8. ✅ **Portainer-friendly** - Standard PostgreSQL container, well-supported

## Rollback (if needed)

If you need to rollback to SQLite:

```bash
# 1. Restore original database.py
cd services/ingest/src
mv database.py database.py.postgres-backup
mv database.py.sqlite-backup database.py

# 2. Restore original config.py changes (manual)
# 3. Remove psycopg2-binary from pyproject.toml
# 4. Run: uv sync
# 5. Update docker-compose.yml to remove postgres service
# 6. Update environment variables back to DATABASE_PATH
```

## Next Steps

1. ✅ **Complete** - All code changes done
2. 🔄 **Start Docker** - `docker-compose up -d postgres`
3. 🔄 **Test** - Run stats/sync commands
4. 🔄 **Update .env** - Add PostgreSQL credentials
5. 🔄 **Deploy** - Push to Portainer
6. 🔄 **Monitor** - Check PostgreSQL logs and metrics

## Files Modified

- ✅ `services/ingest/pyproject.toml` - Added psycopg2-binary
- ✅ `services/ingest/src/config.py` - PostgreSQL config
- ✅ `services/ingest/src/database.py` - PostgreSQL implementation
- ✅ `services/ingest/main.py` - Database initialization
- ✅ `services/ingest/src/processor.py` - Worker function signature
- ✅ `docker-compose.yml` - PostgreSQL service
- ✅ `init_db.sql` - Schema reference
- ✅ `MIGRATION.md` - This document

## Backup Files Created

- `database.py.sqlite-backup` - Original SQLite implementation
- `docker-compose.yml.corrupted-backup` - Corrupted file (can delete)

## Support

If you encounter issues:

1. **Connection errors**: Check PostgreSQL is running and environment variables are set
2. **Permission errors**: Ensure PostgreSQL user has CREATE/ALTER permissions
3. **Schema errors**: Tables are auto-created, but you can manually run `init_db.sql`
4. **Migration errors**: Use `migrate` command or start fresh

---

**Migration completed**: October 29, 2025  
**Migrated by**: GitHub Copilot  
**Status**: ✅ Ready for testing
