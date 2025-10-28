# Quick Start Guide - Direct Search

## ⚡ 5-Minute Setup

### 1. Environment Setup (2 minutes)

```bash
# Required environment variables
export OPENAI_API_KEY="sk-proj-..."
export VECTOR_STORE_ID="vs_..."
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-east-1"
export S3_BUCKET_NAME="your-bucket"
```

### 2. Test the Search (1 minute)

```bash
# Basic search
python direct_search.py "What is Centropa?"

# Full content
python direct_search.py "Ki volt Koltai István?" --full

# More results
python direct_search.py "Holocaust education" --max-results 20
```

### 3. Build Your API (2 minutes)

```python
# minimal_api.py
from fastapi import FastAPI
from direct_search import vector_store_search, get_file_metadata

app = FastAPI()

@app.get("/search")
def search(q: str):
    results = vector_store_search(q, max_results=10)
    
    enriched = []
    for r in results:
        sha256 = r["file_id"].replace("file-", "").split(".")[0]
        meta = get_file_metadata(sha256)
        
        enriched.append({
            "content": r["content"],
            "score": r["score"],
            "filename": meta.get("filename"),
            "drive_url": meta.get("drive_url")
        })
    
    return {"results": enriched}

# Run: uvicorn minimal_api:app
```

## 🎯 Key Features

| Feature | Benefit |
|---------|---------|
| **No LLM** | 5x faster, fixed cost |
| **$2.50/1k searches** | Predictable pricing |
| **0.6-0.9 relevance** | Accurate results |
| **Multilingual** | Hungarian + English |
| **Full metadata** | Drive URLs, S3 URLs |

## 📋 Common Use Cases

### Research Assistant
```bash
python direct_search.py "deportation from Hungary 1944" --full --max-results 5
```

### Content Discovery
```bash
python direct_search.py "tanulási játékok" --preview-length 1000
```

### API Integration
```python
# Your Custom GPT calls this
results = vector_store_search(user_query, max_results=10)
```

## 🔧 Configuration

**Database Path** (edit in direct_search.py):
```python
DB_PATH = "/path/to/your/pipeline.db"
```

**Customize Results**:
```python
# direct_search.py function signature
def vector_store_search(
    query: str,
    max_results: int = 10
) -> List[Dict[str, Any]]:
```

## 📊 Response Format

```json
{
  "file_id": "file-abc123",
  "content": "Document chunk text...",
  "score": 0.8956,
  "attributes": {
    "filename": "koltai-istvan_interjureszlet.docx"
  }
}
```

**After enrichment**:
```json
{
  "filename": "koltai-istvan_interjureszlet.docx",
  "drive_url": "https://drive.google.com/file/d/1ABC.../view",
  "s3_presigned_url": "https://s3.amazonaws.com/...",
  "content": "Full or preview text...",
  "relevance_score": 0.8956
}
```

## 🚀 Deployment Checklist

- [ ] Set environment variables
- [ ] Test with `python direct_search.py "test query"`
- [ ] Copy direct_search.py to your API project
- [ ] Point DB_PATH to your pipeline.db
- [ ] Implement HTTP endpoint (FastAPI/Flask)
- [ ] Add authentication
- [ ] Test with multilingual queries
- [ ] Deploy (Docker/Lambda/Cloud Run)
- [ ] Configure Custom GPT action

## 💡 Pro Tips

1. **Start with 10 results**, adjust based on needs
2. **Use `--full` for research**, short preview for UI
3. **Cache S3 URLs** - they're valid for 1 hour
4. **Log relevance scores** - tune your queries
5. **Test Hungarian + English** - both work perfectly

## 🆘 Troubleshooting

**Empty results?**
- Check VECTOR_STORE_ID is correct
- Verify files are indexed (check pipeline.db)

**Database error?**
- Update DB_PATH in direct_search.py
- Ensure pipeline.db exists

**S3 URL expired?**
- URLs valid for 1 hour
- get_file_metadata() generates fresh URLs

## 📚 Full Documentation

- **README.md** - Complete API guide
- **QUERY_IMPROVEMENTS.md** - Method comparison
- **SPEED_COMPARISON.md** - Performance benchmarks
- **CONTENT_VERIFICATION_REPORT.md** - Accuracy tests

## 🎓 Example Queries

```bash
# English factual
python direct_search.py "What is Kindertransport?"

# Hungarian biographical
python direct_search.py "Ki volt Koltai István?" --full

# Educational content
python direct_search.py "Holocaust education activities"

# Organizational
python direct_search.py "What is Centropa?" --max-results 5

# Event-specific
python direct_search.py "liberation of Auschwitz"
```

---

**Ready to build?** Start with the minimal API example above, then refer to README.md for advanced features.
