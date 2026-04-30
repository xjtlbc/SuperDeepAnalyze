# Async Document Parsing Pipeline Redesign

**Date**: 2026-04-29
**Status**: Approved

## Context

PDF uploads cause the frontend to spin indefinitely. Root cause: `DoclingParser.parse()` is synchronous and CPU-intensive (AI model inference for layout detection + OCR on CPU), called directly from an async handler without `run_in_executor()`. This blocks the entire asyncio event loop — no other requests can be served, no response is returned, and the DB row is only written after everything succeeds.

Docling OCR engines are degraded (`rapidocr` lacks `onnxruntime`, `easyocr` not installed), forcing CPU-only inference that is extremely slow for complex PDFs.

## Design

### 1. Upload Flow: Sync → Async Background

**Before**: Upload handler does parse + chunk + index synchronously, returns only when done.

**After**: Upload handler saves file, inserts DB row with `parse_status='parsing'`, spawns background task, returns immediately.

```
POST /api/documents/upload/{kb_id}
  1. Save file to disk
  2. INSERT documents (parse_status='parsing')
  3. asyncio.create_task(_parse_in_background(doc_id, kb_id, file_path))
  4. Return {id, parse_status: 'parsing'}
```

### 2. Background Parse Function

`_parse_in_background(doc_id, kb_id, file_path)`:

1. Detect file type → route to appropriate parser
2. All sync parsers wrapped in `asyncio.to_thread()` with configurable timeout
3. On success: UPDATE `parse_status='completed'`, save chunks, build FTS5
4. On failure: UPDATE `parse_status='failed'`, store error in `parse_error` column
5. Global timeout: `asyncio.wait_for(task, timeout=settings.parse_timeout_seconds)`

### 3. PDF Smart Routing

**Phase 0 — Quick Probe** (`pdf_probe.py`, <1 second):
- Use `pypdf` to extract text from all pages
- Calculate text density: `total_chars / page_count`
- Route decision:
  - density > 500 chars/page → Docling fast mode (no OCR)
  - density < 100 chars/page → VLM API directly (scanned PDF)
  - middle ground → Docling with OCR, fallback to VLM API on failure/timeout

**Docling Fast Mode**:
```python
PdfPipelineOptions(generate_page_images=False)
```
Skips image generation and OCR for text PDFs, only runs layout model.

**Docling Timeout**: 3 minutes. On timeout → automatic fallback to VLM API.

**VLM API Fallback**:
- PyMuPDF (fitz) renders each page to image
- Each image sent to VLM model via OpenAI-compatible API
- Batch 3-5 pages concurrently
- Aggregate all pages into single Markdown

### 4. New API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /api/documents/{doc_id}/status` | GET | Returns `{parse_status, compile_status, parse_error}` |

### 5. Frontend Changes

**DocumentsTab.tsx**: After upload, show document card with `parse_status: 'parsing'` (gray badge + spinner). Poll `GET /api/documents/{doc_id}/status` every 3 seconds. Transition to `completed` (green) or `failed` (red with error message). Stop polling after 5 minutes (show timeout notice).

**Status badges**:
- `parsing`: gray "解析中" + spinner
- `completed`: green "已解析"
- `failed`: red "解析失败" + error tooltip
- `pending`: amber "待编译"

### 6. Database Changes

Add column to `documents` table:
```sql
ALTER TABLE documents ADD COLUMN parse_error TEXT DEFAULT NULL;
```

### 7. Configuration

New settings in `config.py`:
```python
parse_timeout_seconds: int = 600        # 10 min global parse timeout
docling_timeout_seconds: int = 180      # 3 min Docling-specific timeout
parse_poll_interval_seconds: int = 3    # Frontend poll interval
```

## Files to Modify

| File | Change |
|------|--------|
| `backend/app/api/documents.py` | Major: async background parse + status API |
| `backend/app/services/parsing/dispatcher.py` | Medium: `to_thread` wrappers + PDF routing |
| `backend/app/services/parsing/docling_parser.py` | Medium: fast mode + timeout |
| `backend/app/services/parsing/vlm_ocr.py` | Small: improve concurrency + error handling |
| `backend/app/services/parsing/pdf_probe.py` | New: PDF text density detection |
| `backend/app/models/database.py` | Small: add `parse_error` column |
| `backend/app/config.py` | Small: add timeout configs |
| `frontend/src/components/pages/tabs/DocumentsTab.tsx` | Medium: polling + status badges |

## Verification

1. Upload a text PDF (DOCX exported) → should parse in <30s with Docling fast mode
2. Upload the failing PDF (`fa4a3490e2dcc03c-deepseek_v4.pdf`) → should complete (via VLM API if needed)
3. Upload a DOCX → should work as before
4. Upload an image → VLM API path
5. During parsing, other API requests should still work (event loop not blocked)
6. Backend module imports all pass
7. TypeScript type check passes
8. Frontend build succeeds
