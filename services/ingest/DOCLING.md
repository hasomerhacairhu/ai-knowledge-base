# Docling Processing Engine Integration

## Overview

**Docling** is IBM's advanced document parsing library designed for AI-ready document processing. This system now supports Docling as an alternative processing engine to Unstructured.

## What is Docling?

Docling (by IBM Research) provides:

- **Advanced PDF Understanding**: Superior layout analysis, better table/equation recognition
- **Multiple OCR Engines**: Auto, Tesseract, RapidOCR, EasyOCR, OcrMac (macOS)
- **Faster Processing**: Often 2-3x faster than Unstructured for complex documents
- **Better Quality**: More accurate text extraction for scanned documents and complex layouts
- **Clean Markdown**: Export documents as well-structured markdown
- **Multi-Format Support**: PDF, DOCX, PPTX, images, and more

## Installation

### Option 1: Enable in Dockerfile (Recommended for Production)

Edit `services/ingest/Dockerfile` and uncomment the Docling installation line:

```dockerfile
# Optional: Install docling for advanced document processing (uncomment to enable)
RUN uv pip install docling>=2.0.0
```

Then rebuild:
```bash
cd services/ingest
docker compose build ingest
```

### Option 2: Install Locally (Development)

```bash
cd services/ingest
uv pip install docling>=2.0.0
# Or with pip:
# pip install docling
```

### Option 3: Install with Project Optional Dependencies

```bash
cd services/ingest
uv pip install ".[docling]"
```

## Configuration

Set the processing engine in your `.env` file:

```bash
# Processing Engine: "unstructured" or "docling"
PROCESSING_ENGINE=docling
```

**Available Options:**
- `unstructured` (default) - Uses Unstructured library
- `docling` - Uses IBM Docling library

## Usage

### Using Docling for Processing

Once installed and configured, simply run the normal processing commands:

```bash
# Process files with Docling
python main.py process --max-files 10

# Full pipeline with Docling
python main.py full --max-files 50
```

The system will automatically use Docling based on your `PROCESSING_ENGINE` setting.

### Switching Between Engines

You can switch engines at any time by changing the `.env` file:

```bash
# Switch to Docling
PROCESSING_ENGINE=docling

# Switch back to Unstructured
PROCESSING_ENGINE=unstructured
```

**Note**: Previously processed files remain unchanged. Only new processing jobs use the selected engine.

## Features Comparison

| Feature | Unstructured | Docling |
|---------|-------------|---------|
| **PDF Layout Analysis** | Good | Excellent |
| **OCR Quality** | Good (Tesseract) | Excellent (Multiple engines) |
| **Table Recognition** | Good | Excellent |
| **Equation Support** | Limited | Good (Molecular structures) |
| **Processing Speed** | Moderate | Fast (2-3x for complex docs) |
| **Memory Usage** | Moderate | Low |
| **Output Format** | Text + JSONL | Markdown + JSON |
| **Language Support** | 10+ languages | 10+ languages |
| **Image Processing** | Yes | Yes (better quality) |

## When to Use Each Engine

### Use **Unstructured** for:
- Simple PDFs with good text layers
- Mixed document workflows already tuned
- Environments where Docling cannot be installed
- Documents that are already processing well

### Use **Docling** for:
- **Scanned documents** requiring high-quality OCR
- **Complex layouts** with tables, multi-column text
- **Academic papers** with equations and figures
- **Technical documents** with diagrams
- **Slow processing** files that timeout with Unstructured
- **OCR failures** (114 files in current system)

## OCR Engine Selection

Docling supports multiple OCR engines. The system automatically selects the best available:

1. **Auto** (default) - Automatically selects best engine
2. **Tesseract** - Most compatible, good quality
3. **RapidOCR** - Faster, good for Asian languages
4. **EasyOCR** - High accuracy, slower
5. **OcrMac** - macOS only, uses Apple Vision

### Configuring OCR Engine

Edit `src/docling_processor.py` to change OCR settings:

```python
# Use RapidOCR instead of Tesseract
from docling.datamodel.pipeline_options import RapidOcrOptions
pipeline_options.ocr_options = RapidOcrOptions(
    lang=['eng', 'hun'],
    force_full_page_ocr=False,
)
```

## Performance Tips

### For Scanned Documents:
```bash
# Enable full-page OCR in docling_processor.py
force_full_page_ocr=True
```

### For Large Batches:
```bash
# Process with higher concurrency
PROCESSOR_MAX_WORKERS=20 python main.py process
```

### For Memory Optimization:
```bash
# Use smaller batch sizes
python main.py process --max-files 50
```

## Troubleshooting

### Docling Not Available Error

```bash
❌ Docling engine selected but not installed!
```

**Solution**: Install Docling:
```bash
pip install docling
# Or in Docker:
# Uncomment the RUN line in Dockerfile
```

### Import Errors

If you see `Import "docling.document_converter" could not be resolved`:

1. Check installation: `pip list | grep docling`
2. Reinstall: `pip install --upgrade docling`
3. Verify Python version: Requires Python 3.11+

### Slow Processing

Docling is generally faster, but if slow:

1. Check OCR settings (disable if not needed)
2. Reduce `force_full_page_ocr` usage
3. Use RapidOCR engine for speed

## Architecture

### File Structure

```
services/ingest/src/
├── docling_processor.py    # Docling processing engine
├── processor.py             # Unstructured processing engine (original)
├── config.py                # Configuration with PROCESSING_ENGINE
└── main.py                  # Auto-selects engine based on config
```

### Processing Flow with Docling

```
1. Download file from S3
2. Detect language from filename
3. Configure Docling pipeline (PDF options, OCR settings)
4. Convert document with Docling
5. Extract text as markdown
6. Extract structured elements as JSON
7. Upload artifacts to S3
8. Update database with metadata
```

### Metadata Fields

Docling adds these metadata fields:

```json
{
  "processing_engine": "docling",
  "num_elements": 145,
  "num_chars": 15420,
  "num_pages": 12,
  "docling_version": "2.0.0"
}
```

## Advanced Configuration

### Custom Pipeline Options

Edit `src/docling_processor.py` to customize:

```python
from docling.datamodel.pipeline_options import PdfPipelineOptions

pipeline_options = PdfPipelineOptions()
pipeline_options.do_ocr = True              # Enable OCR
pipeline_options.do_table_structure = True  # Extract tables
pipeline_options.do_picture_classification = True  # Classify images
```

### Language Support

Supported languages (same as Tesseract):

- English (eng), Hungarian (hun), Czech (ces), Slovak (slk)
- Polish (pol), German (deu), French (fra), Spanish (spa)
- Italian (ita), Romanian (ron)

Configure in `_process_with_docling()` function.

## Reprocessing Failed Files with Docling

To reprocess the 114 OCR-failed files with Docling:

```bash
# 1. Switch to Docling
echo "PROCESSING_ENGINE=docling" >> .env

# 2. Reset failed OCR files
docker exec ai-kb-postgres psql -U postgres -d ai_knowledge_base -c \
  "UPDATE file_state SET status='synced', error_message=NULL \
   WHERE error_message LIKE '%No text extracted%';"

# 3. Reprocess with Docling
docker compose run --rm ingest python main.py process --max-files 120
```

## Resources

- **Docling GitHub**: https://github.com/docling-project/docling
- **Documentation**: https://docling-project.github.io/docling/
- **PyPI**: https://pypi.org/project/docling/
- **Examples**: https://github.com/docling-project/docling/tree/main/docs/examples

## Migration Guide

### Switching from Unstructured to Docling

1. **Install Docling** (see Installation section)
2. **Update configuration**: Set `PROCESSING_ENGINE=docling`
3. **Test with small batch**: `python main.py process --max-files 10 --dry-run`
4. **Monitor results**: Check processing success rate
5. **Full rollout**: Process remaining files

### Comparing Results

To compare engines on same files:

```bash
# Process with Unstructured
PROCESSING_ENGINE=unstructured python main.py process --max-files 10

# Reset and reprocess with Docling
# (Reset files in DB first)
PROCESSING_ENGINE=docling python main.py process --max-files 10

# Compare text outputs in S3
```

## Support

For issues or questions:
1. Check [Docling Documentation](https://docling-project.github.io/docling/)
2. Review [GitHub Issues](https://github.com/docling-project/docling/issues)
3. Check this project's issue tracker
