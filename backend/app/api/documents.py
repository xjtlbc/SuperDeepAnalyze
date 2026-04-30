"""Document upload and parsing API."""

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

from app.config import settings
from app.models.database import get_connection
from app.services.parsing.dispatcher import ParserDispatcher
from app.services.parsing.chunking import chunk_text
from app.services.parsing.excel_parser import ExcelParser
from app.services.parsing.types import DocType
from app.services.compilation.l2_compiler import L2Compiler
from app.services.compilation.cache_manager import CacheManager

router = APIRouter(prefix="/api/documents", tags=["documents"])
logger = logging.getLogger("app.documents")

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

CHAPTER_PATTERNS = [
    re.compile(r'^第[一二三四五六七八九十百千万\d]+\s*[章节回卷集篇幕]'),
    re.compile(r'^#\s*(第.+)$'),
    re.compile(r'^Chapter\s+\d+', re.IGNORECASE),
    re.compile(r'^卷[一二三四五六七八九十百千万\d]+'),
]
VOLUME_PATTERNS = [
    re.compile(r'^第[一二三四五六七八九十百千万\d]+\s*卷'),
    re.compile(r'^卷[一二三四五六七八九十百千万\d]+$'),
]


class DocumentResponse(BaseModel):
    id: str
    kb_id: str
    filename: str
    file_hash: str
    file_size: int
    file_type: str
    parse_status: str
    compile_status: str = "pending"
    chunk_count: int = 0


@router.post("/upload/{kb_id}", response_model=DocumentResponse)
async def upload_document(kb_id: str, file: UploadFile = File(...)):
    """
    Upload a document to a knowledge base.
    1. Save file
    2. Parse using dispatcher
    3. Chunk
    4. L2 compile
    """
    # Verify KB exists
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT id FROM knowledge_bases WHERE id = ?", (kb_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Knowledge base not found")
    finally:
        conn.close()

    # Save file
    doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    doc_dir = settings.KB_DIR / kb_id / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename to prevent path traversal
    safe_filename = os.path.basename(file.filename or "upload")
    file_path = doc_dir / safe_filename
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        shutil.rmtree(doc_dir, ignore_errors=True)
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_FILE_SIZE // (1024*1024)}MB)")
    with open(file_path, "wb") as f:
        f.write(content)

    # Check for cross-KB duplicate (same file_hash, already compiled)
    file_hash = hashlib.sha256(content).hexdigest()
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT kb_id, id FROM documents WHERE file_hash = ? AND parse_status = 'completed' LIMIT 1",
            (file_hash,),
        )
        dup_row = cursor.fetchone()
    finally:
        conn.close()

    if dup_row:
        source_kb_id = dup_row["kb_id"]
        source_doc_id = dup_row["id"]
        source_doc_dir = settings.KB_DIR / source_kb_id / "documents" / source_doc_id
        if (source_doc_dir / "l1_summaries.json").exists():
            # Reuse compiled document
            cache_mgr = CacheManager()
            if cache_mgr.reuse_compiled_doc(file_hash, kb_id, doc_id, source_kb_id, source_doc_id):
                conn = get_connection()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute(
                        """INSERT INTO documents (id, kb_id, filename, file_hash, file_size, file_type, parse_status, compile_status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (doc_id, kb_id, safe_filename, file_hash, len(content),
                         _infer_file_type(safe_filename), "completed", "completed"),
                    )
                    conn.execute(
                        "UPDATE knowledge_bases SET compile_status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (kb_id,),
                    )
                    conn.commit()
                finally:
                    conn.close()

                # Count chunks
                chunks_dir = settings.KB_DIR / kb_id / "documents" / doc_id / "l2_chunks"
                chunk_count = len(list(chunks_dir.glob("*.md"))) if chunks_dir.exists() else 0

                return DocumentResponse(
                    id=doc_id,
                    kb_id=kb_id,
                    filename=safe_filename,
                    file_hash=file_hash,
                    file_size=len(content),
                    file_type=_infer_file_type(safe_filename),
                    parse_status="completed",
                    compile_status="completed",
                    chunk_count=chunk_count,
                )
            # reuse_compiled_doc failed — fall through to normal parsing

    # Check same-KB duplicate (same file already uploaded to this KB)
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT id, parse_status FROM documents WHERE kb_id = ? AND file_hash = ? LIMIT 1",
            (kb_id, file_hash),
        )
        same_kb_dup = cursor.fetchone()
    finally:
        conn.close()

    if same_kb_dup:
        # Clean up the duplicate doc_dir we created
        shutil.rmtree(doc_dir, ignore_errors=True)
        dup_doc_id = same_kb_dup["id"]
        # Determine compile_status from filesystem evidence
        dup_l1_path = settings.KB_DIR / kb_id / "documents" / dup_doc_id / "l1_summaries.json"
        dup_compile_status = "completed" if dup_l1_path.exists() else "pending"
        return DocumentResponse(
            id=dup_doc_id,
            kb_id=kb_id,
            filename=safe_filename,
            file_hash=file_hash,
            file_size=len(content),
            file_type=_infer_file_type(safe_filename),
            parse_status=same_kb_dup["parse_status"],
            compile_status=dup_compile_status,
            chunk_count=0,
        )

    # Insert DB row with parse_status='parsing' — return immediately
    file_type = _infer_file_type(safe_filename)
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO documents (id, kb_id, filename, file_hash, file_size, file_type, parse_status, compile_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, kb_id, safe_filename, file_hash, len(content), file_type, "parsing", "pending"),
        )
        conn.execute(
            "UPDATE knowledge_bases SET compile_status = 'partial', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (kb_id,),
        )
        conn.commit()
    finally:
        conn.close()

    # Spawn background parsing
    asyncio.create_task(_parse_in_background(doc_id, kb_id, file_path, safe_filename, file_hash))

    return DocumentResponse(
        id=doc_id,
        kb_id=kb_id,
        filename=safe_filename,
        file_hash=file_hash,
        file_size=len(content),
        file_type=file_type,
        parse_status="parsing",
        compile_status="pending",
        chunk_count=0,
    )


async def _parse_in_background(doc_id: str, kb_id: str, file_path: Path, safe_filename: str, file_hash: str):
    """Background task: parse -> chunk -> compile -> update DB."""
    try:
        await asyncio.wait_for(
            _do_parse(doc_id, kb_id, file_path, safe_filename, file_hash),
            timeout=settings.parse_timeout_seconds,
        )
    except asyncio.TimeoutError:
        _update_parse_status(doc_id, "failed", f"Parse timed out after {settings.parse_timeout_seconds}s")
        logger.error("Parse timeout for doc %s", doc_id)
    except Exception as e:
        _update_parse_status(doc_id, "failed", str(e)[:500])
        logger.error("Parse failed for doc %s: %s", doc_id, e)


async def _do_parse(doc_id: str, kb_id: str, file_path: Path, safe_filename: str, file_hash: str):
    """Actual parse/chunk/compile logic, extracted from upload handler."""
    from app.models.crud import load_model_configs

    # Get VLM config (optional)
    vlm_config = None
    try:
        model_configs = load_model_configs()
        if model_configs and model_configs.vlm:
            vlm_config = model_configs.vlm
    except Exception:
        pass

    dispatcher = ParserDispatcher(vlm_config=vlm_config)

    # Parse
    parsed = await dispatcher.parse(file_path, doc_id, kb_id)

    # Save parsed content
    doc_dir = settings.KB_DIR / kb_id / "documents" / doc_id
    parsed_path = doc_dir / "parsed.md"
    with open(parsed_path, "w", encoding="utf-8") as f:
        f.write(parsed.content)

    # Chunk
    if parsed.file_type in (DocType.XLSX, DocType.CSV):
        excel_parser = ExcelParser()
        chunks = excel_parser.parse_to_chunks(str(file_path), doc_id, kb_id, parsed.file_hash)
    else:
        chunks = chunk_text(parsed.content, doc_id=doc_id, kb_id=kb_id, file_hash=parsed.file_hash)

    # L2 compile
    l2_compiler = L2Compiler()
    l2_compiler.save_chunks(chunks, kb_id, doc_id)
    l2_compiler.build_fts_index(chunks)

    # Update DB to completed
    _update_parse_status(doc_id, "completed")
    logger.info("Parse completed for doc %s (%d chunks)", doc_id, len(chunks))


def _update_parse_status(doc_id: str, status: str, error: str | None = None):
    """Update document parse_status and parse_error in DB."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE documents SET parse_status = ?, parse_error = ? WHERE id = ?",
            (status, error, doc_id),
        )
        conn.commit()
    finally:
        conn.close()


def _infer_file_type(filename: str) -> str:
    """Infer file type from extension."""
    ext = Path(filename).suffix.lower()
    type_map = {
        ".pdf": "pdf", ".docx": "docx", ".doc": "docx",
        ".txt": "text", ".md": "text",
        ".xlsx": "xlsx", ".xls": "xlsx", ".csv": "xlsx",
    }
    return type_map.get(ext, "text")


@router.get("/list/{kb_id}")
async def list_documents(kb_id: str):
    """List all documents in a knowledge base."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT id, kb_id, filename, file_hash, file_size, file_type, parse_status, compile_status, parse_error, created_at FROM documents WHERE kb_id = ? ORDER BY created_at DESC",
            (kb_id,),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "kb_id": row["kb_id"],
                "filename": row["filename"],
                "file_hash": row["file_hash"],
                "file_size": row["file_size"],
                "file_type": row["file_type"],
                "parse_status": row["parse_status"],
                "compile_status": row["compile_status"],
                "parse_error": row["parse_error"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    finally:
        conn.close()


@router.get("/{doc_id}")
async def get_document(doc_id: str):
    """Get document details."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT id, kb_id, filename, file_hash, file_size, file_type, parse_status, compile_status, created_at FROM documents WHERE id = ?",
            (doc_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        return dict(row)
    finally:
        conn.close()


@router.get("/{doc_id}/status")
async def get_document_status(doc_id: str):
    """Get document parse/compile status for polling."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT parse_status, compile_status, parse_error FROM documents WHERE id = ?",
            (doc_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        return {
            "parse_status": row["parse_status"],
            "compile_status": row["compile_status"],
            "parse_error": row["parse_error"],
        }
    finally:
        conn.close()
async def get_document_chunks(doc_id: str, kb_id: str):
    """Get L2 chunks for a document."""
    chunks_dir = settings.KB_DIR / kb_id / "documents" / doc_id / "l2_chunks"
    if not chunks_dir.exists():
        return []

    chunks = []
    for f in sorted(chunks_dir.glob("*.md")):
        with open(f, "r", encoding="utf-8") as fh:
            content = fh.read()
        chunks.append({
            "filename": f.name,
            "chunk_id": f.stem,
            "content_preview": content[:200],
        })
    return chunks


@router.get("/{kb_id}/{doc_id}/chunks/{chunk_id}")
async def get_chunk_content(kb_id: str, doc_id: str, chunk_id: str):
    """Get a specific L2 chunk's full content for evidence source viewing."""
    chunk_path = settings.KB_DIR / kb_id / "documents" / doc_id / "l2_chunks" / f"{chunk_id}.md"
    if not chunk_path.exists():
        raise HTTPException(status_code=404, detail="Chunk not found")
    content = chunk_path.read_text(encoding="utf-8")
    return {"doc_id": doc_id, "chunk_id": chunk_id, "content": content}


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str):
    """Delete a document and all its associated data (DB, FTS5, filesystem, FAISS)."""
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT kb_id FROM documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        kb_id = row["kb_id"]

        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.execute("DELETE FROM fts_content WHERE doc_id = ?", (doc_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Delete filesystem artifacts
    doc_dir = settings.KB_DIR / kb_id / "documents" / doc_id
    if doc_dir.exists():
        shutil.rmtree(doc_dir)

    # Delete FAISS indexes for this document
    faiss_dir = settings.FAISS_DIR / kb_id / doc_id
    if faiss_dir.exists():
        shutil.rmtree(faiss_dir)

    # Update KB compile status
    conn = get_connection()
    try:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE kb_id = ?", (kb_id,)
        ).fetchone()[0]
        status = "pending" if remaining == 0 else "partial"
        conn.execute(
            "UPDATE knowledge_bases SET compile_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, kb_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return None


# ─── Document Detail APIs ───

@router.get("/{doc_id}/detail")
async def get_document_detail(doc_id: str, kb_id: str = Query(...)):
    """Get document overview: basic info + L1/L2 stats."""
    doc_dir = settings.KB_DIR / kb_id / "documents" / doc_id
    if not doc_dir.exists():
        raise HTTPException(status_code=404, detail="Document directory not found")

    # L1 stats
    l1_path = doc_dir / "l1_summaries.json"
    l1_batch_count = 0
    l1_total_chunks = 0
    if l1_path.exists():
        with open(l1_path, "r", encoding="utf-8") as f:
            l1_data = json.load(f)
        if isinstance(l1_data, list):
            l1_batch_count = len(l1_data)
            for entry in l1_data:
                l1_total_chunks += len(entry.get("chunk_ids", []))

    # L2 stats
    chunks_dir = doc_dir / "l2_chunks"
    l2_chunk_count = len(list(chunks_dir.glob("*.md"))) if chunks_dir.exists() else 0

    # DB info
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        db_info = dict(row) if row else {}
    finally:
        conn.close()

    # KB compile status
    compile_status = "unknown"
    conn = get_connection()
    try:
        kb_row = conn.execute("SELECT compile_status FROM knowledge_bases WHERE id = ?", (kb_id,)).fetchone()
        if kb_row:
            compile_status = kb_row["compile_status"]
    finally:
        conn.close()

    return {
        "document": db_info,
        "kb_compile_status": compile_status,
        "l1_summary": {
            "batch_count": l1_batch_count,
            "total_chunks_covered": l1_total_chunks,
        },
        "l2_summary": {
            "chunk_count": l2_chunk_count,
        },
    }


@router.get("/{doc_id}/l1-summaries")
async def get_l1_summaries(doc_id: str, kb_id: str = Query(...), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    """Get L1 summaries with pagination."""
    l1_path = settings.KB_DIR / kb_id / "documents" / doc_id / "l1_summaries.json"
    if not l1_path.exists():
        return {"summaries": [], "total": 0, "offset": offset, "limit": limit}

    with open(l1_path, "r", encoding="utf-8") as f:
        all_summaries = json.load(f)

    total = len(all_summaries) if isinstance(all_summaries, list) else 0
    page = all_summaries[offset:offset + limit] if isinstance(all_summaries, list) else []

    return {"summaries": page, "total": total, "offset": offset, "limit": limit}


@router.get("/{doc_id}/l2-toc")
async def get_l2_toc(doc_id: str, kb_id: str = Query(...)):
    """Get L2 table of contents with full chapter detection."""
    chunks_dir = settings.KB_DIR / kb_id / "documents" / doc_id / "l2_chunks"
    if not chunks_dir.exists():
        return {"chapters": [], "total_chunks": 0}

    chunk_files = sorted(chunks_dir.glob("*.md"))
    total_chunks = len(chunk_files)

    # Scan for chapter detection — read only first 2048 bytes per chunk
    # (chapter titles always appear near the top)
    SCAN_BYTES = 2048
    chapters = []
    for i, chunk_file in enumerate(chunk_files):
        with open(chunk_file, "r", encoding="utf-8") as f:
            preview = f.read(SCAN_BYTES)

        sep_idx = preview.find("\n---\n")
        text = preview[sep_idx + 5:].strip() if sep_idx != -1 else preview

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            is_volume = any(p.match(line) for p in VOLUME_PATTERNS)
            is_chapter = any(p.match(line) for p in CHAPTER_PATTERNS)
            if is_chapter or is_volume:
                chapters.append({
                    "name": line,
                    "chunk_index": i,
                    "is_volume": is_volume,
                })
                break  # Only first match per chunk

    # Compute end_index: each chapter spans from its start to the next chapter's start - 1
    enriched_chapters = []
    for ci, ch in enumerate(chapters):
        if ci + 1 < len(chapters):
            end_idx = chapters[ci + 1]["chunk_index"] - 1
        else:
            end_idx = total_chunks - 1
        enriched_chapters.append({
            "name": ch["name"],
            "chunk_index": ch["chunk_index"],
            "chunk_end": end_idx,
            "is_volume": ch["is_volume"],
        })

    # Fallback: synthetic ranges if no chapters detected
    if not chapters and total_chunks > 0:
        range_size = 100
        for i in range(0, total_chunks, range_size):
            end_range = min(i + range_size - 1, total_chunks - 1)
            enriched_chapters.append({
                "name": f"片段 #{i} - #{end_range}",
                "chunk_index": i,
                "chunk_end": end_range,
                "is_volume": False,
            })

    return {
        "chapters": enriched_chapters,
        "total_chunks": total_chunks,
    }


@router.get("/{doc_id}/l2-batch")
async def get_l2_batch(doc_id: str, kb_id: str = Query(...), indices: str = Query(...)):
    """Get multiple L2 chunks by index, with overlap deduplication and TOC stripping."""
    chunks_dir = settings.KB_DIR / kb_id / "documents" / doc_id / "l2_chunks"
    if not chunks_dir.exists():
        return {"chunks": []}

    chunk_files = sorted(chunks_dir.glob("*.md"))
    index_list = [int(i) for i in indices.split(",") if i.strip().isdigit()]

    results = []
    for idx in index_list:
        if 0 <= idx < len(chunk_files):
            with open(chunk_files[idx], "r", encoding="utf-8") as f:
                content = f.read()
            # Strip YAML-like header
            sep_idx = content.find("\n---\n")
            text = content[sep_idx + 5:].strip() if sep_idx != -1 else content.strip()
            results.append({"index": idx, "content": text})

    if not results:
        return {"chunks": [], "merged_content": "", "total": 0}

    # Sort by index
    results.sort(key=lambda x: x["index"])

    # Strip TOC blocks from the FIRST chunk only.
    # When a chapter starts at chunk N, that chunk may contain a table-of-contents
    # listing all chapters. We strip it so only the actual chapter content remains.
    results[0]["content"] = _strip_toc_block(results[0]["content"])

    # Merge overlapping chunks
    merged = [results[0]["content"]]
    for i in range(1, len(results)):
        prev = merged[-1]
        curr = results[i]["content"]
        overlap = _find_overlap(prev, curr)
        if overlap > 0:
            merged.append(curr[overlap:])
        else:
            merged.append(curr)
    merged_content = "\n\n".join(merged)

    return {"chunks": results, "merged_content": merged_content, "total": len(results)}


def _strip_toc_block(content: str) -> str:
    """Strip a TOC block from the beginning of chunk content.

    Strategy (same as DeepAnalyze stripBeforeChapterHeader):
    1. Find blocks of consecutive chapter-pattern lines.
    2. If a block has 3+ entries (likely a TOC), find where the first chapter name
       repeats — the actual chapter starts from that repeated name.
    3. If no repeat, the last entry in the TOC block is the actual chapter header.
    4. If no TOC block, return from the first chapter header.
    """
    lines = content.split("\n")
    blocks = []
    i = 0
    while i < len(lines):
        trimmed = lines[i].strip()
        if not trimmed:
            i += 1
            continue
        is_chapter_line = any(p.match(trimmed) for p in CHAPTER_PATTERNS)
        if not is_chapter_line:
            i += 1
            continue

        names = []
        end = i
        for j in range(i, len(lines)):
            next_trimmed = lines[j].strip()
            if not next_trimmed:
                break
            if any(p.match(next_trimmed) for p in CHAPTER_PATTERNS):
                names.append(next_trimmed)
                end = j
            else:
                break

        blocks.append({"start": i, "end": end, "count": len(names), "names": names})
        i = end + 1

    if not blocks:
        return content

    # Find first TOC block (3+ consecutive chapter names)
    for b_idx, block in enumerate(blocks):
        if block["count"] >= 3:
            # Look for first chapter name repeating
            first_name = block["names"][0]
            for n in range(1, len(block["names"])):
                if block["names"][n] == first_name:
                    # Find the line corresponding to this repeat
                    name_counter = 0
                    for l in range(block["start"], block["end"] + 1):
                        line_t = lines[l].strip()
                        if line_t and any(p.match(line_t) for p in CHAPTER_PATTERNS):
                            if name_counter == n:
                                return "\n".join(lines[l:]).strip()
                            name_counter += 1
                    break

            # No repeat found — if there's a next block, start from it
            if b_idx + 1 < len(blocks):
                return "\n".join(lines[blocks[b_idx + 1]["start"]:]).strip()

            # Otherwise, start from the last entry of the TOC block
            return "\n".join(lines[block["end"]:]).strip()

    # No TOC block — return from first chapter header
    return "\n".join(lines[blocks[0]["start"]:]).strip()


@router.get("/{doc_id}/l0-entities")
async def get_l0_entities(doc_id: str, kb_id: str = Query(...)):
    """Get L0 entities referenced in this document's L1 summaries."""
    doc_dir = settings.KB_DIR / kb_id / "documents" / doc_id
    l1_path = doc_dir / "l1_summaries.json"
    entities_path = settings.KB_DIR / kb_id / "l0" / "entities.json"

    if not l1_path.exists():
        return {"entities": [], "entity_count": 0}

    # Collect unique entity names from L1
    entity_names = set()
    with open(l1_path, "r", encoding="utf-8") as f:
        l1_data = json.load(f)
    if isinstance(l1_data, list):
        for entry in l1_data:
            for name in entry.get("entities_mentioned", []):
                entity_names.add(name)

    # Match with L0 entities
    l0_entities = []
    if entities_path.exists():
        with open(entities_path, "r", encoding="utf-8") as f:
            all_entities = json.load(f)
        for e in all_entities:
            if isinstance(e, dict) and e.get("name") in entity_names:
                l0_entities.append({
                    "name": e.get("name"),
                    "type": e.get("type", "unknown"),
                    "attributes": e.get("attributes", {}),
                })

    return {"entities": l0_entities, "entity_count": len(l0_entities)}


def _find_overlap(prev: str, curr: str, max_check: int = 500) -> int:
    """Find the longest prefix of curr that matches a suffix of prev."""
    max_len = min(max_check, len(curr), len(prev))
    for length in range(max_len, 5, -1):
        if prev[-length:] == curr[:length]:
            return length
    return 0


@router.get("/{kb_id}/{doc_id}/parsed")
async def get_document_parsed(kb_id: str, doc_id: str):
    """Get full parsed document content (parsed.md)."""
    parsed_path = settings.KB_DIR / kb_id / "documents" / doc_id / "parsed.md"
    if not parsed_path.exists():
        raise HTTPException(status_code=404, detail="No parsed content found")
    return {"content": parsed_path.read_text(encoding="utf-8")}
