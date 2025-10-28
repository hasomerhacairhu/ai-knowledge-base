# Query Module Improvements for E-Learning & Research

## Overview
Enhanced the `query_with_grounding.py` script to provide comprehensive source attribution and multiple output formats suitable for e-learning development, content creation, and research workflows.

## Key Improvements

### 1. **Complete Source Attribution** ✅
- Lists all 200+ documents in the knowledge base with full metadata
- Shows original filenames from Google Drive
- Displays file paths showing content organization
- Identifies document types (PDF, Word, PowerPoint, etc.)
- Provides direct Drive URLs for each source document

### 2. **Multiple Output Formats** ✅

#### **Standard Format** (Default)
```bash
uv run python query_with_grounding.py "Your question"
```
- Clean, human-readable terminal output
- Organized sections: Query, Answer, Sources, Usage, Timestamp
- Perfect for interactive research and exploration
- Shows all available documents with clickable Drive links

#### **JSON Format** (API Integration)
```bash
uv run python query_with_grounding.py "Your question" --format json
```
- Structured data for programmatic access
- Includes full document metadata in `available_sources` array
- Easy integration with learning management systems (LMS)
- Machine-readable for automation and analytics

#### **Markdown Format** (Documentation)
```bash
uv run python query_with_grounding.py "Your question" --format markdown
```
- Ready for documentation platforms (GitHub, GitBook, Notion)
- Formatted for inclusion in learning materials
- Clickable citations and source links
- Easy to convert to PDF or HTML for distribution

### 3. **Educational Metadata** ✅
Each source document includes:
- **Original Name**: Exact filename from Google Drive
- **Path**: Folder structure showing content organization
- **Document Type**: Categorized (PDF Document, Word Document, PowerPoint, etc.)
- **Drive URL**: Direct link to view in Google Drive
- **MIME Type**: Technical file format information

### 4. **Database-Driven Approach** ✅
Instead of relying on the Responses API's limited metadata, we:
- Query our own SQLite database (`drive_file_mapping` table)
- Match SHA256 hashes to original Drive files
- Provide complete attribution even when API doesn't expose details
- Show all available sources, not just those cited

## Use Cases

### For E-Learning Content Developers
```bash
# Get content with all sources for lesson planning
uv run python query_with_grounding.py "What happened during Kristallnacht?" --format markdown > lesson_sources.md
```
- Use the markdown output directly in lesson plans
- Reference specific Drive documents for student materials
- Create bibliographies automatically

### For Researchers
```bash
# Export data for analysis
uv run python query_with_grounding.py "Hungarian Jewish history" --format json > research_data.json
```
- Analyze source coverage
- Track document usage patterns
- Build research databases

### For Content Creators
```bash
# Interactive exploration with full source listing
uv run python query_with_grounding.py "Tell me about Centropa"
```
- See all 200 documents that could inform the answer
- Click through to primary sources
- Verify information against original materials

## Technical Details

### Database Schema
```sql
CREATE TABLE drive_file_mapping (
    drive_file_id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    drive_path TEXT,
    original_name TEXT,
    drive_created_time TEXT,
    drive_modified_time TEXT,
    drive_mime_type TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### Document Type Categorization
Automatically categorizes documents by MIME type:
- `application/pdf` → PDF Document
- `application/vnd.openxmlformats-officedocument.wordprocessingml.document` → Word Document
- `application/vnd.openxmlformats-officedocument.presentationml.presentation` → PowerPoint
- `text/plain` → Text File
- And more...

### Source Retrieval Function
```python
def get_all_knowledge_base_files() -> List[Dict]:
    """Retrieve all files from the database (our knowledge base sources)."""
    # Queries SQLite database
    # Returns list with: original_name, drive_path, mime_type, 
    #                    drive_file_id, content_hash, drive_url, document_type
```

## Example Output

### Standard Format
```
====================================================================================================
📚 KNOWLEDGE BASE QUERY RESULT
====================================================================================================

❓ QUERY:
----------------------------------------------------------------------------------------------------
   What is Centropa's mission?

📝 ANSWER:
----------------------------------------------------------------------------------------------------
Centropa's mission focuses on preserving and promoting Jewish history, culture, and heritage...

📚 KNOWLEDGE BASE SOURCES:
----------------------------------------------------------------------------------------------------
The following documents were available for this query:

 1. 00_2018_ps_fv_family_history_films_-_student_project_guide_-_annotated_teachers_version_.docx
    📁 Path: Centropa/...
    📄 Type: Word Document
    🔗 View: https://drive.google.com/file/d/1ajF5kTDJMXIEL9g1kkAB3Kwy7tmUjfzJ/view

[... 200 total documents listed ...]

💡 Total documents in knowledge base: 200
🎯 Vector Store ID: vs_6900e6fc7c94819187c6ec114fd3adc9
```

## Benefits

### ✅ **Full Transparency**
- See exactly which documents are in your knowledge base
- Verify source material quality
- Identify gaps in coverage

### ✅ **Educational Standards**
- Proper citation and attribution
- Links to primary sources
- Supports academic integrity

### ✅ **Content Development**
- Quick access to source materials
- Easy to reference specific documents
- Streamlined content creation workflow

### ✅ **Research Quality**
- Traceable information sources
- Verifiable claims
- Academic-grade documentation

## Query Method Comparison: Three-Tier Optimization

We now have **three different query methods**, each optimized for specific use cases:

| Method | Script | LLM Used | Cost per Query | Speed | Output Type | Best For |
|--------|--------|----------|----------------|-------|-------------|----------|
| **Full Featured** | `query_with_grounding.py` | ✅ gpt-4o-mini | ~$0.0015-0.0025 | Moderate (7-10s) | Natural language answer + 200 sources | E-learning content, research with citations |
| **Quick Query** | `quick_query.py` | ✅ gpt-4o-mini | ~$0.0015 | Fast (7-8s) | Natural language answer + token metrics | Simple Q&A, cost tracking |
| **Direct Search** | `direct_search.py` | ❌ **NO LLM** | **$0.0025 fixed** | **Instant (1-2s)** | Document chunks + relevance + Drive/S3 URLs | Raw semantic search, file access, custom processing |

### 1. Full Featured Query (`query_with_grounding.py`)
**When to use:**
- Creating lesson plans with full source attribution
- Research requiring complete bibliography
- Content development needing Drive URLs
- Academic work requiring citations

**Features:**
- Natural language answer from LLM
- All 200 documents listed with metadata
- Multiple output formats (standard/JSON/markdown)
- Database integration for Drive URLs
- Complete transparency

**Example:**
```bash
uv run python query_with_grounding.py "What is Centropa?" --format markdown
```

### 2. Quick Query (`quick_query.py`)
**When to use:**
- Fast answers without database overhead
- Cost tracking and budgeting
- Simple Q&A workflows
- Lightweight API integration

**Features:**
- Natural language answer from LLM
- Token usage and cost display
- Reduced max_num_results (10 vs 20)
- No database lookups
- Clean, minimal output

**Example:**
```bash
uv run python quick_query.py "What is Centropa?"
# Output: Answer + "Tokens: 9,704, Cost: $0.001522"
```

### 3. Direct Search (`direct_search.py`) - **BREAKTHROUGH** 🚀
**When to use:**
- Building custom LLM solutions on top of search results
- Need fastest possible response time
- Want to avoid LLM hallucinations (raw source text only)
- Analyzing document relevance patterns
- Batch processing many queries
- Cost optimization (fixed price per search)
- Need direct access to source files (Drive + S3)

**Features:**
- **NO LLM MODEL** - pure semantic search
- Document chunks with relevance scores (0.0-1.0)
- File IDs and filenames
- Raw content previews
- Metadata attributes
- **Instant results** - no generation latency
- **Full metadata enrichment**:
  - Original filenames from Google Drive
  - Clickable Google Drive URLs
  - S3 presigned URLs (valid for 1 hour)
  - File paths and MIME types
  - Complete file provenance

**Technical Details:**
- Uses OpenAI Vector Store Search API endpoint
- Direct HTTP POST via httpx library
- Database integration (SQLite) for metadata
- S3 client for presigned URL generation
- Endpoint: `POST https://api.openai.com/v1/vector_stores/{id}/search`
- Request: `{"query": "...", "max_num_results": 10, "rewrite_query": true}`
- Response: `{"search_query": "...", "data": [{"score": 0.6417, "filename": "...", "content": [...]}]}`
- Enrichment: Queries `file_state` and `drive_file_mapping` tables by SHA256

**Example:**
```bash
uv run python direct_search.py "What is Centropa?" --max-results 3

# Output:
# [1] 📄 411597fde11023620255a6282150b2698027ef3e290ca7b02349e09c8a44e137.txt
#     🎯 Relevance Score: 0.6417
#     🆔 File ID: file-A84mVMXfUAnn6P5zQvZz6o
#     📝 Original Filename: kindertransport_engl.pdf
#     📁 Drive Path: Centropa/kindertransport_engl.pdf
#     📄 MIME Type: application/pdf
#     🔗 Drive URL: https://drive.google.com/file/d/1E_aA4NMJqtH2S0Z9O39uLv82KB0wRU3s/view
#     ☁️  S3 Signed URL (1h): https://fra1.digitaloceanspaces.com/somer-ai/objects/...
#     📝 Content Preview: CentropaStudent.org lesson plan: Kindertransport...
```

**Multilingual Support:**
```bash
# Works seamlessly with Hungarian queries
uv run python direct_search.py "Ki volt Koltai?" --max-results 2

# Returns:
# [1] koltai-istvan_interjureszlet.docx
#     🔗 Drive URL + ☁️ S3 Signed URL
#     Content: "Koltai István – Panni férje..."
```

**Cost Advantage:**
- Direct search: $2.50 per 1,000 searches = **$0.0025 per query**
- LLM queries: ~15-20k tokens × $0.150/1M = **$0.0015-0.003 per query**
- Break-even: Direct search is cost-competitive and **much faster**

**Speed Advantage:**
- Direct search: **1-2 seconds** (semantic search + DB lookup)
- LLM queries: **7-10 seconds** (search + generation)
- Speed up: **4-5x faster** for document retrieval
- Metadata enrichment adds <100ms overhead

**Data Enrichment:**
- SHA256 extracted from OpenAI filename
- Database join with `file_state` and `drive_file_mapping`
- S3 presigned URLs generated on-demand (1 hour expiry)
- Complete file provenance for every result

### Use Case Decision Tree

```
Do you need natural language answers?
│
├─ YES → Do you need all 200 sources with Drive URLs?
│   │
│   ├─ YES → Use query_with_grounding.py (Full Featured)
│   └─ NO → Use quick_query.py (Quick Query)
│
└─ NO → Use direct_search.py (Direct Search)
    └─ Build your own processing on top of document chunks
```

## Future Enhancements

Potential additions:
- [x] Direct search + database join for Drive URLs ✅ **COMPLETED**
- [x] S3 presigned URL generation ✅ **COMPLETED**
- [ ] Custom LLM on top of direct search results
- [ ] Metadata filtering in direct search
- [ ] Pagination for large result sets
- [ ] Batch query processing
- [ ] Automatic citation formatting (APA, MLA, Chicago)
- [ ] Multi-language source filtering
- [ ] Topic clustering of source documents
- [ ] JSON output format for direct search
- [ ] Export search results to CSV/Excel

## Conclusion

The enhanced query system now provides **three optimization tiers** for different use cases:

1. **query_with_grounding.py** - Full-featured for e-learning and research with complete source attribution
2. **quick_query.py** - Lightweight for simple Q&A with cost tracking
3. **direct_search.py** - Revolutionary NO-LLM direct semantic search with full metadata enrichment

The discovery of OpenAI's Vector Store Search API endpoint, combined with **database integration for Drive URLs and S3 presigned URLs**, enables **instant document retrieval with complete file access** - opening possibilities for custom processing, faster responses, predictable costs, and direct file downloads.
