# Dockerfile for AI Knowledge Base Ingest Pipeline
# Optimized for DigitalOcean App Platform or Droplet

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-hun \
    tesseract-ocr-eng \
    tesseract-ocr-ces \
    tesseract-ocr-slk \
    tesseract-ocr-pol \
    poppler-utils \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Verify Tesseract installation
RUN tesseract --version && tesseract --list-langs

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY main.py ./

# Install Python dependencies using uv
# First install uv itself
RUN pip install --no-cache-dir uv

# Install project dependencies
RUN uv sync --frozen

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import pytesseract; pytesseract.get_tesseract_version()"

# Default command (can be overridden)
CMD ["uv", "run", "python", "main.py", "--help"]
