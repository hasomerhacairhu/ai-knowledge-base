# AI Knowledge Base Ingest Pipeline

A robust document ingestion pipeline that syncs documents from Google Drive, processes them with Unstructured.io, stores them in S3, and indexes them in OpenAI Vector Stores for semantic search.

## 🎯 Purpose

This pipeline is designed to **ingest and prepare documents** for AI-powered knowledge retrieval systems. It handles the complete workflow from Google Drive to OpenAI Vector Stores, making your documents searchable via semantic AI.

**Note**: This repository handles **ingestion only**. For querying the vector store and building Custom GPT APIs, see the **[api-reference/](api-reference/)** folder.

## � Repository Organization

This repository is organized into **two clear sections**:

### 🔧 Root Directory (Ingestion Pipeline)
**Purpose**: Sync documents from Google Drive to OpenAI Vector Stores

**Key files**:
- `main.py` - Pipeline entry point
- `src/` - Pipeline source code (drive_sync, processor, indexer)
- `data/pipeline.db` - SQLite database tracking file state

**Use this for**: Setting up and running the document ingestion workflow

### 🚀 api-reference/ Folder (Query API Reference)
**Purpose**: Sample implementation for querying the vector store (for your future Custom GPT API)

**Key files**:
- `direct_search.py` - Search implementation (NO LLM required)
- `README.md` - Complete API integration guide
- `QUICK_START.md` - 5-minute setup guide
- Performance benchmarks and accuracy reports

**Use this for**: Building your Custom GPT API, implementing semantic search

### 📚 Quick Links

- **[api-reference/QUICK_START.md](api-reference/QUICK_START.md)** - 5-minute API setup
- **[api-reference/README.md](api-reference/README.md)** - Complete API guide

## 🏗️ Architecture

```
┌─────────────────┐
│  Google Drive   │
│  (Source docs)  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  1. SYNC (drive_sync.py)                │
│     - List changed files                │
│     - Download from Drive               │
│     - Upload to S3                      │
│     - Store metadata in SQLite          │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  2. PROCESS (processor.py)              │
│     - Fetch from S3                     │
│     - Process with Unstructured.io      │
│     - Extract text, tables, images      │
│     - Save structured data to S3        │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  3. INDEX (indexer.py)                  │
│     - Upload to OpenAI                  │
│     - Add to Vector Store               │
│     - Enable semantic search            │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  OpenAI Vector  │
│     Store       │
│  (Searchable)   │
└─────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Google Cloud service account with Drive API access
- AWS S3 bucket
- OpenAI API key with Vector Store access
- Unstructured.io API key (optional, for cloud processing)

### Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd ai-knowledge-base-ingest

# Install dependencies with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

### Configuration

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` with your credentials:
```env
# Google Drive
GOOGLE_CREDENTIALS_FILE=path/to/service-account.json
DRIVE_FOLDER_ID=your-drive-folder-id

# AWS S3
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-bucket-name

# OpenAI
OPENAI_API_KEY=sk-proj-...
VECTOR_STORE_ID=vs_...

# Unstructured.io (optional)
UNSTRUCTURED_API_KEY=your-api-key
UNSTRUCTURED_API_URL=https://api.unstructuredapp.io/general/v0/general
```

## 📖 Usage

### Basic Commands

```bash
# Full pipeline - sync, process, and index
uv run python main.py

# Individual stages
uv run python main.py sync              # Sync from Drive to S3
uv run python main.py process           # Process files with Unstructured
uv run python main.py index             # Index files to OpenAI

# Dry run (test without changes)
uv run python main.py --dry-run sync

# Limit number of files
uv run python main.py --max-files 10 sync
```

### Pipeline Stages

#### 1. Sync Stage
Syncs files from Google Drive to S3:
- Lists all files in the configured Drive folder (recursive)
- Detects changes using modification timestamps and SHA256 hashes
- Downloads changed files from Drive
- Uploads to S3 with metadata
- Exports Google Workspace files (Docs, Sheets, Slides) to Office formats
- Stores file state in SQLite database

```bash
uv run python main.py sync --max-files 100
```

#### 2. Process Stage
Processes files with Unstructured.io:
- Fetches raw files from S3
- Extracts text, tables, and images
- Structures content into chunks
- Saves processed output back to S3
- Supports 30+ file formats (PDF, DOCX, PPTX, images, etc.)

```bash
uv run python main.py process --max-files 50
```

#### 3. Index Stage
Indexes processed files to OpenAI Vector Store:
- Uploads processed text files to OpenAI
- Adds files to Vector Store
- Enables semantic search
- Updates database with OpenAI file IDs

```bash
uv run python main.py index --max-files 50
```

## 🗄️ Database Schema

The pipeline uses SQLite to track file state:

```sql
-- Main file tracking table
CREATE TABLE file_state (
    id INTEGER PRIMARY KEY,
    sha256 TEXT UNIQUE NOT NULL,
    s3_key TEXT NOT NULL,
    original_name TEXT NOT NULL,
    mime_type TEXT,
    size_bytes INTEGER,
    status TEXT NOT NULL,
    synced_at TIMESTAMP,
    processed_at TIMESTAMP,
    indexed_at TIMESTAMP,
    openai_file_id TEXT,
    error_message TEXT
);

-- Google Drive file mapping
CREATE TABLE drive_file_mapping (
    id INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL,
    drive_file_id TEXT NOT NULL,
    drive_file_name TEXT NOT NULL,
    drive_parent_path TEXT,
    drive_modified_time TIMESTAMP,
    FOREIGN KEY (sha256) REFERENCES file_state(sha256)
);
```

## 📁 Project Structure

```
ai-knowledge-base-ingest/
├── main.py                  # Main entry point
├── purge.py                 # Cleanup utility
├── pyproject.toml           # Dependencies
├── docker-compose.yml       # Docker setup
├── Dockerfile               # Container definition
├── .env                     # Configuration (not in git)
├── .env.example             # Configuration template
├── data/                    # Database and temp files
│   └── pipeline.db          # SQLite database
├── src/                     # Source code
│   ├── config.py            # Configuration management
│   ├── database.py          # Database operations
│   ├── drive_sync.py        # Google Drive sync
│   ├── processor.py         # Unstructured.io processing
│   ├── indexer.py           # OpenAI indexing
│   └── utils.py             # Shared utilities
└── api-reference/           # API reference for querying
    ├── README.md            # API documentation
    ├── direct_search.py     # Vector store search sample
    └── *.md                 # Analysis and benchmarks
```

## 🔧 Advanced Usage

### Dry Run Mode

Test the pipeline without making changes:
```bash
uv run python main.py --dry-run sync
uv run python main.py --dry-run process
```

### Limit Files

Process only a subset of files:
```bash
uv run python main.py --max-files 5 sync
uv run python main.py --max-files 10 process
```

### Verbose Logging

Enable detailed debug output:
```bash
uv run python main.py --verbose sync
```

### Purge Data

Clean up all data (⚠️ destructive):
```bash
uv run python purge.py
```

Options:
- `--all` - Delete everything (database, S3, OpenAI)
- `--s3` - Delete only S3 objects
- `--openai` - Delete only OpenAI files
- `--db` - Delete only database

## 🐳 Docker Deployment

### Using Docker Compose

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Using Docker Directly

```bash
# Build image
docker build -t knowledge-ingest .

# Run container
docker run -d \
  --name knowledge-ingest \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  knowledge-ingest
```

## 📊 Monitoring

The pipeline provides detailed progress tracking:

```
Syncing from Google Drive...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
✓ Successfully synced 10 files

Processing with Unstructured.io...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:30
✓ Successfully processed 10 files

Indexing to OpenAI Vector Store...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:01:00
✓ Successfully indexed 10 files
```

Check database for file status:
```bash
sqlite3 data/pipeline.db "SELECT status, COUNT(*) FROM file_state GROUP BY status"
```

## 🔍 Supported File Types

The pipeline supports 30+ file formats:

**Documents**: PDF, DOCX, DOC, ODT, RTF, TXT, MD  
**Spreadsheets**: XLSX, XLS, CSV, ODS  
**Presentations**: PPTX, PPT, ODP  
**Images**: JPG, PNG, TIFF (with OCR)  
**Google Workspace**: Docs, Sheets, Slides (auto-converted)  
**Archives**: ZIP (auto-extracted)  
**Email**: EML, MSG  

## 🚦 File Processing States

Files move through these states:

1. **synced** - Downloaded from Drive, uploaded to S3
2. **processed** - Processed by Unstructured.io
3. **indexed** - Indexed in OpenAI Vector Store
4. **error** - Processing failed (check error_message)

## 🔗 Integration with Custom GPT API

After ingestion, documents are searchable via OpenAI Vector Stores. See the `api-reference/` folder for:

- **direct_search.py** - Sample implementation for semantic search
- **README.md** - Complete API integration guide
- Performance benchmarks and test results
- Code samples for FastAPI, Flask, Express

The API reference shows how to:
- Query the vector store without using an LLM (5x faster, cheaper)
- Enrich results with Drive URLs and S3 presigned URLs
- Build Custom GPT actions
- Handle multilingual content

## 🐛 Troubleshooting

### Common Issues

**Google Drive authentication fails**
```bash
# Check service account file exists
ls -la your-service-account.json

# Verify Drive API is enabled
# Check permissions in Google Cloud Console
```

**S3 upload fails**
```bash
# Test AWS credentials
aws s3 ls s3://your-bucket-name/

# Check IAM permissions (s3:PutObject, s3:GetObject)
```

**OpenAI indexing fails**
```bash
# Verify API key
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/models

# Check vector store exists
# Verify API key has vector store access
```

**Processing fails**
```bash
# Check Unstructured.io API key
curl -H "unstructured-api-key: $UNSTRUCTURED_API_KEY" \
  https://api.unstructuredapp.io/general/v0/general

# Try processing locally (no API key needed)
# Set UNSTRUCTURED_API_KEY="" in .env
```

### Debug Mode

Enable detailed logging:
```bash
uv run python main.py --verbose sync 2>&1 | tee debug.log
```

Check database state:
```bash
sqlite3 data/pipeline.db

# List all tables
.tables

# Check file states
SELECT status, COUNT(*) FROM file_state GROUP BY status;

# View recent errors
SELECT original_name, error_message, synced_at 
FROM file_state 
WHERE status = 'error' 
ORDER BY synced_at DESC 
LIMIT 10;
```

## 📈 Performance

Typical processing times:
- **Sync**: ~1-2 seconds per file (depends on Drive API)
- **Process**: ~5-10 seconds per file (depends on Unstructured.io)
- **Index**: ~2-3 seconds per file (depends on OpenAI API)

Batch recommendations:
- Start with `--max-files 10` to test
- Scale up to `--max-files 100` for production
- Use `--dry-run` to preview changes

## 🔒 Security

- Keep `.env` file secure (never commit to git)
- Use least-privilege IAM policies for S3
- Rotate API keys regularly
- Use service accounts for Google Drive (not personal accounts)
- Limit Drive folder access to only necessary files
- Enable S3 bucket encryption
- Use presigned URLs with short expiration (1 hour)

## 🤝 Contributing

This is an internal tool, but improvements are welcome:

1. Test changes thoroughly with `--dry-run`
2. Update documentation
3. Check error handling
4. Verify database migrations

## 📝 License

Internal use only.

## 🆘 Support

For issues with:
- **Ingestion pipeline**: Check this README and troubleshooting section
- **API integration**: See `api-reference/README.md`
- **Custom GPT setup**: Refer to API reference documentation

---

## 🔄 Workflow Overview

```
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: INGEST (Root Directory)                           │
│  ─────────────────────────────────────────────────────────  │
│  Run: uv run python main.py                                 │
│                                                              │
│  1. Sync from Google Drive to S3                            │
│  2. Process with Unstructured.io                            │
│  3. Index to OpenAI Vector Store                            │
│                                                              │
│  Result: Documents searchable in vector store               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: BUILD API (api-reference/)                        │
│  ─────────────────────────────────────────────────────────  │
│  Reference: api-reference/README.md                         │
│  Sample: api-reference/direct_search.py                     │
│                                                              │
│  1. Copy direct_search.py to your API project              │
│  2. Implement HTTP endpoint (FastAPI/Flask/Express)        │
│  3. Deploy your API                                         │
│  4. Connect Custom GPT                                      │
│                                                              │
│  Result: Custom GPT can query your knowledge base          │
└─────────────────────────────────────────────────────────────┘
```

**Ingestion**: Keeps vector store up-to-date with latest documents (run periodically)  
**API**: Queries vector store on-demand for Custom GPT (always-on service)

---

## 📦 Version Control

### What to Commit

✅ **Safe to commit**:
- All source code (`main.py`, `src/`, `api-reference/`)
- Documentation files (`.md`)
- Configuration templates (`.env.example`)
- Docker files (`Dockerfile`, `docker-compose.yml`)
- Dependencies (`pyproject.toml`, `uv.lock`)

⚠️ **Check .gitignore before committing**:
- `.env` (should be ignored - contains secrets)
- `data/pipeline.db` (may contain sensitive file metadata)
- `*.json` (service account credentials)

❌ **Never commit**:
- `.env` file with credentials
- Service account JSON files
- Database with production data
- API keys or secrets

### Suggested Commit Message

```bash
git add -A
git commit -m "refactor: Separate ingestion pipeline from API reference

Reorganized repository for clear separation of concerns:

ADDED:
- Comprehensive documentation for ingestion and API
- api-reference/ folder with complete integration guide
- Enhanced direct_search.py with --full and --preview-length options

REMOVED FROM ROOT:
- Query tools and documentation (moved to api-reference/)

BENEFITS:
- Clear separation: ingestion vs API development
- Better documentation structure
- Ready for Custom GPT API integration"

git push origin main
```

---

## 🎓 Next Steps

### For Ingestion Setup
1. ✅ Read this README
2. ✅ Configure `.env` with your credentials
3. ✅ Run `uv run python main.py --dry-run sync` to test
4. ✅ Run full pipeline: `uv run python main.py`

### For API Development
1. ✅ Go to `api-reference/` folder
2. ✅ Read `QUICK_START.md` (5 minutes)
3. ✅ Test: `uv run python api-reference/direct_search.py "test query"`
4. ✅ Review code samples in `README.md`
5. ✅ Copy to your API project and deploy

---

**Ready to start?**
1. Configure `.env` with your credentials
2. Run `uv run python main.py --dry-run sync` to test
3. Process files with `uv run python main.py`
4. Build your API using `api-reference/` as a guide
