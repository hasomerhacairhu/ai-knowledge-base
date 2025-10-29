# AI Knowledge Base API

FastAPI service for semantic search over the AI Knowledge Base using OpenAI Vector Store.

## Features

- RESTful API for semantic search
- Automatic metadata enrichment (Drive URLs, S3 presigned URLs)
- CORS support
- Health check endpoints
- Interactive API documentation (Swagger UI)

## Endpoints

- `GET /` - Service information
- `GET /health` - Health check
- `POST /api/search` - Semantic search (JSON body)
- `GET /api/search?q=...` - Semantic search (URL params)
- `GET /docs` - Interactive API documentation

## Development

```bash
cd services/api
uv sync
uv run uvicorn main:app --reload --port 8000
```

## Environment Variables

See `.env` in the root directory.

Required:
- `OPENAI_API_KEY`
- `VECTOR_STORE_ID`
- `DATABASE_PATH`
- S3 credentials for presigned URLs
