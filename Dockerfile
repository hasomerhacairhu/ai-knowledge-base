# Dockerfile for AI Knowledge Base Ingest Pipeline
# Optimized for DigitalOcean App Platform or Droplet

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (minimal - poppler for PDFs, libmagic, and Tesseract OCR)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libmagic1 \
    libgomp1 \
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
    && rm -rf /var/lib/apt/lists/*

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

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD tesseract --version && python -c "import pytesseract; print('Tesseract ready')"

# Default command (can be overridden)
CMD ["uv", "run", "python", "main.py", "--help"]
