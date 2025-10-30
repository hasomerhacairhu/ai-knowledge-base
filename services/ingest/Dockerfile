# Dockerfile for AI Knowledge Base Ingest Pipeline
# Optimized for DigitalOcean App Platform or Droplet

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (minimal - poppler for PDFs, libmagic, Tesseract OCR, and pandoc for EPUB)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libmagic1 \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-hun \
    tesseract-ocr-ces \
    tesseract-ocr-slk \
    tesseract-ocr-pol \
    tesseract-ocr-deu \
    tesseract-ocr-fra \
    tesseract-ocr-spa \
    tesseract-ocr-ita \
    tesseract-ocr-ron \
    pandoc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set uv environment variables for isolated venv
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Copy dependency files first (for layer caching)
COPY pyproject.toml ./
COPY uv.lock ./
COPY .python-version ./

# Create virtual environment and install dependencies
RUN uv venv /app/.venv
RUN uv sync --frozen --no-dev

# Install pypandoc explicitly (required for EPUB processing)
RUN uv pip install pypandoc>=1.13

# Install docling for advanced document processing
RUN uv pip install docling>=2.0.0

# Copy application code
COPY src/ ./src/
COPY main.py ./
COPY purge.py ./

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD tesseract --version && /app/.venv/bin/python -c "import pytesseract; print('Tesseract ready')"

# Default command (can be overridden)
CMD ["/app/.venv/bin/python", "main.py", "--help"]
