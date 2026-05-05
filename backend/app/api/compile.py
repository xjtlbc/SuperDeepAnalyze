"""Compilation trigger API."""

import asyncio
import json
import logging
import traceback
import uuid
from pathlib import Path
from typing import Callable, Optional, Union

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger("app.compile")

from app.config import settings
from app.models.config import RoleType
from app.models.crud import load_model_configs
from app.models.database import get_connection
from app.models.router import ModelRouter
from app.services.compilation.l0_compiler import L0Compiler
from app.services.compilation.l1_compiler import L1Compiler
from app.services.compilation.l2_compiler import L2Compiler
from app.services.compilation.cache_manager import CacheManager
from app.services.compilation.entity_merger import merge_kb_entities
from app.services.subagent_dispatcher import SubagentDispatcher
from app.services.llm.client import LLMClient
from app.services.parsing.chunking import chunk_text
from app.services.parsing.docling_parser import compute_file_hash
from app.services.compilation.abstract_generator import (
    generate_doc_abstract, save_abstract,
)

router = APIRouter(prefix="/api/compile", tags=["compile"])

_EXCEL_EXTENSIONS = frozenset({".xlsx", ".xls", ".xlsb", ".csv"})


def _update_compile_detail(doc_id: str, stage: str) -> None:
    """Mark a compilation stage as completed in compile_detail for a document."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT compile_detail FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        detail = json.loads(row["compile_detail"]) if row and row["compile_detail"] else {}
        detail.setdefault("stages", {})
        detail["stages"][stage] = True
        conn.execute(
            "UPDATE documents SET compile_detail = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(detail, ensure_ascii=False), doc_id),
        )
        conn.commit()
    except Exception as e:
        logger.warning("Failed to update compile_detail for %s: %s", doc_id, e)
    finally:
        conn.close()


def _validate_artifacts(kb_id: str, doc_id: str) -> dict:
    """Validate that expected compilation artifacts exist on disk.

    Returns a dict with boolean flags for each stage:
      - l2_compiled: FAISS index or FTS5 data exists
      - l1_compiled: l1_summaries.json exists and is valid JSON
      - entities_merged: entities.json exists at KB level
    """
    result = {"l2_compiled": False, "l1_compiled": False, "entities_merged": False}

    # L2: FAISS index at FAISS_DIR/kb_id/l2_{doc_id}.index
    faiss_path = settings.FAISS_DIR / kb_id / f"l2_{doc_id}.index"
    if faiss_path.exists():
        result["l2_compiled"] = True
    else:
        # Fallback: check FTS5 data in DB
        try:
            conn = get_connection()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM fts_content WHERE doc_id = ?",
                    (doc_id,),
                ).fetchone()
                if row and row["cnt"] > 0:
                    result["l2_compiled"] = True
            finally:
                conn.close()
        except Exception:
            pass

    # L1: l1_summaries.json exists and is valid JSON
    l1_path = settings.KB_DIR / kb_id / "documents" / doc_id / "l1_summaries.json"
    if l1_path.exists():
        try:
            with open(l1_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                result["l1_compiled"] = True
        except (json.JSONDecodeError, OSError):
            pass

    # Entities: entities.json at KB level
    entities_path = settings.KB_DIR / kb_id / "l0" / "entities.json"
    if entities_path.exists():
        result["entities_merged"] = True

    return result

# Global state for active compilations: kb_id -> {"cancel_event": asyncio.Event}
_active_compilations: dict[str, dict] = {}


async def _send_progress(progress_cb: Callable, data: dict):
    """Send progress, handling both sync and async callbacks."""
    result = progress_cb(data)
    if asyncio.iscoroutine(result):
        await result


async def run_compilation(
    kb_id: str,
    progress_cb: Callable,
    cancel_event: Optional[asyncio.Event] = None,
    sample: bool = False,
    l1_mode: str = "fast",
):
    """Run full L0/L1/L2 compilation with progress callbacks.

    Args:
        l1_mode: L1 compilation mode — "fast" (1 doc-level abstract per doc),
                 "standard" (batch summaries, same as before), or "deep"
                 (standard + cross-reference analysis).
        sample: If True, large documents (>500 chunks) use ~20% uniform sampling for L1.
    """
    await _send_progress(progress_cb, {"type": "status", "phase": "parsing", "progress": 5, "message": "加载模型配置..."})

    # Load model config
    db_configs = load_model_configs()
    if not db_configs:
        raise RuntimeError("No model configuration found")

    router_obj = ModelRouter()
    router_obj.register(db_configs)
    llm_client = LLMClient(router_obj)

    # Get all documents for this KB (only those needing compilation)
    doc_conn = get_connection()
    try:
        cursor = doc_conn.execute(
            "SELECT id, kb_id, filename FROM documents WHERE kb_id = ? AND parse_status = 'completed'",
            (kb_id,),
        )
        docs = cursor.fetchall()
    finally:
        doc_conn.close()

    if not docs:
        raise RuntimeError("No parsed documents found")

    all_chunks = []
    all_l1_results = []
    accumulated_l1_results: list[dict] = []
    total_docs = len(docs)
    skipped_count = 0

    L1_BATCH_SIZE = 50

    for i, doc in enumerate(docs):
        doc_id = doc["id"]
        doc_name = doc["filename"] if doc["filename"] else doc_id

        # Check for cancellation
        if cancel_event and cancel_event.is_set():
            await _send_progress(progress_cb, {
                "type": "paused",
                "progress": int(10 + 65 * i / total_docs),
                "message": f"编译已暂停，已完成 {i}/{total_docs} 个文档",
            })
            # Update DB status
            conn = get_connection()
            try:
                conn.execute(
                    "UPDATE knowledge_bases SET compile_status = 'paused', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (kb_id,),
                )
                conn.commit()
            finally:
                conn.close()
            return {
                "kb_id": kb_id,
                "status": "paused",
                "documents_processed": i,
                "documents_skipped": skipped_count,
                "chunks_generated": len(all_chunks),
                "l1_summaries": len(all_l1_results),
            }

        # Check if this document has already been fully compiled (L1 summaries exist and complete)
        l1_path = settings.KB_DIR / kb_id / "documents" / doc_id / "l1_summaries.json"
        if l1_path.exists():
            with open(l1_path, "r", encoding="utf-8") as f:
                existing_l1 = json.load(f)

            # Determine total expected batches by counting unique chunks
            chunk_ids_seen = set()
            for entry in existing_l1:
                chunk_ids_seen.update(entry.get("chunk_ids", []))

            # Re-chunk to find total (fast, no LLM call)
            parsed_path = settings.KB_DIR / kb_id / "documents" / doc_id / "parsed.md"
            if parsed_path.exists():
                with open(parsed_path, "r", encoding="utf-8") as f:
                    content = f.read()
                all_chunks_for_check = chunk_text(content, doc_id=doc_id, kb_id=kb_id)
                total_expected = len(all_chunks_for_check)

                if len(chunk_ids_seen) >= total_expected:
                    # Validate artifacts before skipping
                    artifacts = _validate_artifacts(kb_id, doc_id)
                    if artifacts["l2_compiled"] and artifacts["l1_compiled"]:
                        # Fully compiled with valid artifacts, skip
                        _update_compile_detail(doc_id, "l2_compiled")
                        _update_compile_detail(doc_id, "l1_compiled")
                        await _send_progress(progress_cb, {
                            "type": "status",
                            "phase": "skipping_existing",
                            "progress": 10 + int(30 * i / total_docs),
                            "message": f"跳过已有 L1 摘要: {doc_name} ({i+1}/{total_docs})",
                        })
                        all_l1_results.extend(existing_l1)
                        skipped_count += 1
                        continue
                    else:
                        # Status says completed but artifacts are missing — re-compile
                        logger.warning(
                            "Document %s marked completed but artifacts invalid (l2=%s, l1=%s), re-compiling",
                            doc_id, artifacts["l2_compiled"], artifacts["l1_compiled"],
                        )
                else:
                    # Partial results — resume from where we left off
                    await _send_progress(progress_cb, {
                        "type": "status",
                        "phase": "compiling_l1",
                        "progress": 10 + int(30 * i / total_docs),
                        "message": f"L1 摘要 {doc_name} — 检测到部分结果 ({len(existing_l1)}/{total_expected} 批)，继续编译剩余...",
                    })
            else:
                # No parsed content, skip entirely
                continue
        else:
            existing_l1 = []

        # Load parsed content
        parsed_path = settings.KB_DIR / kb_id / "documents" / doc_id / "parsed.md"
        if not parsed_path.exists():
            continue

        with open(parsed_path, "r", encoding="utf-8") as f:
            content = f.read()

        await _send_progress(progress_cb, {
            "type": "status",
            "phase": "compiling_l2",
            "progress": 10 + int(30 * i / total_docs),
            "message": f"L2 索引 {doc_name} ({i+1}/{total_docs}) — 正在分块...",
        })

        # Chunk — use Excel-specific chunking for spreadsheet files
        is_excel = Path(doc_name).suffix.lower() in _EXCEL_EXTENSIONS
        excel_analysis = None

        if is_excel:
            original_path = settings.KB_DIR / kb_id / "documents" / doc_id / doc_name
            if original_path.exists():
                try:
                    from app.services.parsing.excel_parser import ExcelParser
                    ep = ExcelParser()
                    chunks = ep.parse_to_chunks(
                        original_path, doc_id, kb_id,
                        file_hash=compute_file_hash(original_path) if original_path.exists() else "",
                    )
                    excel_analysis = getattr(chunks, "excel_analysis", None)
                    logger.info("Excel-specific chunking: %d chunks for %s", len(chunks), doc_name)
                except Exception as e:
                    logger.warning("Excel chunking failed for %s, falling back to generic: %s", doc_name, e)
                    chunks = chunk_text(content, doc_id=doc_id, kb_id=kb_id)
            else:
                chunks = chunk_text(content, doc_id=doc_id, kb_id=kb_id)
        else:
            chunks = chunk_text(content, doc_id=doc_id, kb_id=kb_id)
        all_chunks.extend(chunks)

        # If resuming with partial L1 results, filter out already-processed chunks
        if existing_l1:
            processed_chunk_ids = set()
            for entry in existing_l1:
                processed_chunk_ids.update(entry.get("chunk_ids", []))
            remaining_chunks = [c for c in chunks if c.chunk_id not in processed_chunk_ids]

            if not remaining_chunks:
                # All chunks already processed, just use existing results
                await _send_progress(progress_cb, {
                    "type": "status",
                    "phase": "skipping_existing",
                    "progress": 10 + int(30 * i / total_docs),
                    "message": f"跳过已有 L1 摘要: {doc_name} ({i+1}/{total_docs})",
                })
                all_l1_results.extend(existing_l1)
                skipped_count += 1
                continue

            # Skip L2 re-compilation (already done for this doc)
            await _send_progress(progress_cb, {
                "type": "status",
                "phase": "compiling_l1",
                "progress": 40 + int(30 * i / total_docs),
                "message": f"L1 摘要 {doc_name} — L2 已有索引，编译剩余 {len(remaining_chunks)} 个文本块...",
            })
            chunks = remaining_chunks
        else:
            embedding_provider = router_obj.get_provider(RoleType.EMBEDDING)
            if embedding_provider:
                await _send_progress(progress_cb, {
                    "type": "status",
                    "phase": "compiling_l2",
                    "progress": 10 + int(30 * (i + 0.5) / total_docs),
                    "message": f"L2 索引 {doc_name} — {len(chunks)} 个文本块，正在构建向量与关键词索引...",
                })
            else:
                await _send_progress(progress_cb, {
                    "type": "status",
                    "phase": "compiling_l2",
                    "progress": 10 + int(30 * (i + 0.5) / total_docs),
                    "message": f"L2 索引 {doc_name} — {len(chunks)} 个文本块，仅构建关键词索引（未配置向量模型）...",
                })

            # L2 compile (FAISS + FTS5, or FTS5 only if no embedding)
            l2 = L2Compiler(embedding_provider=embedding_provider)
            await l2.compile(chunks, kb_id, doc_id)
            _update_compile_detail(doc_id, "l2_compiled")

            await _send_progress(progress_cb, {
                "type": "status",
                "phase": "compiling_l1",
                "progress": 40 + int(30 * i / total_docs),
                "message": f"L1 摘要 {doc_name} ({i+1}/{total_docs}) — 共 {(len(chunks) + L1_BATCH_SIZE - 1) // L1_BATCH_SIZE} 批，开始生成...",
            })

        # L1 compile: sample mode for very large documents
        SAMPLE_THRESHOLD = 500
        compile_chunks = chunks
        if sample and len(chunks) > SAMPLE_THRESHOLD:
            step = max(1, len(chunks) // int(len(chunks) * 0.2))
            compile_chunks = chunks[::step]
            await _send_progress(progress_cb, {
                "type": "status",
                "phase": "compiling_l1",
                "progress": 40 + int(30 * i / total_docs),
                "message": f"[采样模式] {doc_name}: {len(chunks)} chunks → {len(compile_chunks)} chunks (20% 采样)",
            })

        doc_l1_results: list[dict] = []
        total_batches = (len(compile_chunks) + L1_BATCH_SIZE - 1) // L1_BATCH_SIZE
        use_accel = total_batches > 200

        def make_l1_cb(dn: str, total: int):
            async def cb(msg: str):
                await _send_progress(progress_cb, {
                    "type": "status",
                    "phase": "compiling_l1",
                    "progress": 40 + int(30 * (i + 0.5) / total_docs),
                    "message": f"L1 摘要 {dn}: {msg}",
                })
            return cb

        def make_save_cb():
            async def cb(partial_results: list[dict]):
                nonlocal doc_l1_results
                doc_l1_results = partial_results
                l1.save(partial_results, kb_id, doc_id)
            return cb

        l1 = L1Compiler(llm_client)

        # ── L1 mode selection ──────────────────────────────────────
        if l1_mode == "fast":
            # Fast mode: single doc-level abstract, skip batch summarization
            await _send_progress(progress_cb, {
                "type": "status",
                "phase": "compiling_fast",
                "progress": 40 + int(30 * i / total_docs),
                "message": f"L1 快速摘要 {doc_name} ({i+1}/{total_docs}) — 生成文档级摘要...",
            })

            # Generate one abstract per document (reuse L1's abstract generator)
            abstract_data = await generate_doc_abstract(
                llm_client, [{"chunk_ids": [c.chunk_id for c in compile_chunks],
                              "summary": content[:4000]}],
                doc_name=doc_name,
            )
            abstract_data["doc_id"] = doc_id
            save_abstract(abstract_data, kb_id, doc_id)

            # Build L1 results from abstract (single entry)
            l1_results = [{
                "chunk_ids": [c.chunk_id for c in compile_chunks],
                "summary": abstract_data.get("abstract", content[:500]),
                "entities_mentioned": abstract_data.get("key_entities") or abstract_data.get("entities_top5") or [],
                "relations": [],
                "contradictions": [],
                "metadata": {"l1_mode": "fast", "doc_id": doc_id},
            }]

        elif l1_mode == "deep":
            # Deep mode: standard batch summaries + cross-reference analysis
            await _send_progress(progress_cb, {
                "type": "status",
                "phase": "compiling_l1",
                "progress": 40 + int(30 * i / total_docs),
                "message": f"L1 深度摘要 {doc_name} ({i+1}/{total_docs}) — {total_batches} 批，深度模式...",
            })
            if is_excel and excel_analysis:
                l1_results = [await l1.generate_excel_l1(
                    analysis=excel_analysis, chunks=compile_chunks,
                    filename=doc_name, kb_id=kb_id,
                )]
            elif use_accel:
                l1_results = await l1.compile_batch_pool(
                    compile_chunks, batch_size=L1_BATCH_SIZE,
                    progress_cb=make_l1_cb(doc_name, total_batches),
                    save_cb=make_save_cb(),
                )
            else:
                l1_results = await l1.compile_batch(
                    compile_chunks, batch_size=L1_BATCH_SIZE,
                    progress_cb=make_l1_cb(doc_name, total_batches),
                    save_cb=make_save_cb(),
                )

        else:
            # Standard mode: per-batch summarization (original behavior)
            if excel_analysis and is_excel:
                await _send_progress(progress_cb, {
                    "type": "status",
                    "phase": "compiling_l1",
                    "progress": 40 + int(30 * i / total_docs),
                    "message": f"L1 Excel摘要 {doc_name} — 使用结构化分析数据（{len(chunks)} chunks）...",
                })
                l1_results = [await l1.generate_excel_l1(
                    analysis=excel_analysis,
                    chunks=compile_chunks,
                    filename=doc_name,
                    kb_id=kb_id,
                )]
            elif use_accel:
                await _send_progress(progress_cb, {
                    "type": "status",
                    "phase": "acceleration_mode",
                    "progress": 40 + int(30 * i / total_docs),
                    "message": f"L1 摘要 {doc_name} — {total_batches} 批，[加速池] 4 worker (2轻+2主) 并发执行",
                })
                l1_results = await l1.compile_batch_pool(
                    compile_chunks,
                    batch_size=L1_BATCH_SIZE,
                    progress_cb=make_l1_cb(doc_name, total_batches),
                    save_cb=make_save_cb(),
                )
            else:
                l1_results = await l1.compile_batch(
                    compile_chunks,
                    batch_size=L1_BATCH_SIZE,
                    progress_cb=make_l1_cb(doc_name, total_batches),
                    save_cb=make_save_cb(),
                )

        # Merge with existing partial results if resuming
        if existing_l1:
            all_results = existing_l1 + l1_results
        else:
            all_results = l1_results

        l1.save(all_results, kb_id, doc_id)
        doc_l1_results = all_results
        all_l1_results.extend(all_results)

        # Mark this document as fully compiled (L1+L2 done; L0 is KB-level)
        _update_compile_detail(doc_id, "l1_compiled")
        doc_conn = get_connection()
        try:
            doc_conn.execute(
                "UPDATE documents SET compile_status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (doc_id,),
            )
            doc_conn.commit()
        finally:
            doc_conn.close()

    await _send_progress(progress_cb, {
        "type": "status",
        "phase": "merging_entities",
        "progress": 85,
        "message": f"合并全局实体图谱 (基于 {len(all_l1_results)} 条摘要)...",
    })

    # Merge entities from L1 results (no LLM call needed)
    if all_l1_results:
        entity_count, timeline_count = merge_kb_entities(all_l1_results, kb_id)
        # Mark entities_merged for all documents in this KB
        for doc in docs:
            _update_compile_detail(doc["id"], "entities_merged")
        await _send_progress(progress_cb, {
            "type": "status",
            "phase": "entities_merged",
            "progress": 95,
            "message": f"实体合并完成: {entity_count} 个实体, {timeline_count} 条时间线事件",
        })

    # Run artifact validation before reporting completion
    validated_count = 0
    failed_validation: list[str] = []
    for doc in docs:
        artifacts = _validate_artifacts(kb_id, doc["id"])
        if artifacts["l2_compiled"] and artifacts["l1_compiled"]:
            validated_count += 1
        else:
            failed_validation.append(doc["id"])
    if failed_validation:
        logger.warning(
            "Compilation artifacts missing for %d/%d documents: %s",
            len(failed_validation), len(docs), failed_validation[:5],
        )

    await _send_progress(progress_cb, {
        "type": "status",
        "phase": "done",
        "progress": 100,
        "message": f"编译完成! {len(docs)} 文档, {len(all_chunks)} chunks, {len(all_l1_results)} 摘要 (已验证 {validated_count}/{len(docs)})",
    })

    # Auto-trigger Wiki generation as background task
    asyncio.create_task(_auto_generate_wiki(kb_id))

    return {
        "kb_id": kb_id,
        "status": "completed",
        "documents_processed": len(docs),
        "documents_skipped": skipped_count,
        "chunks_generated": len(all_chunks),
        "l1_summaries": len(all_l1_results),
    }


async def _compile_single_document(
    kb_id: str,
    doc_id: str,
    doc_name: str,
    llm_client,
    progress_cb,
    cancel_event: asyncio.Event | None = None,
) -> dict:
    """Compile L1+L2 for a single document. Used by parallel dispatcher."""
    from app.models.config import RoleType
    from app.services.compilation.l1_compiler import L1Compiler
    from app.services.compilation.l2_compiler import L2Compiler

    L1_BATCH_SIZE = 50

    # Check if already fully compiled — validate artifacts before skipping
    l1_path = settings.KB_DIR / kb_id / "documents" / doc_id / "l1_summaries.json"
    if l1_path.exists():
        with open(l1_path, "r", encoding="utf-8") as f:
            existing_l1 = json.load(f)
        parsed_path = settings.KB_DIR / kb_id / "documents" / doc_id / "parsed.md"
        if parsed_path.exists():
            with open(parsed_path, "r", encoding="utf-8") as f:
                content = f.read()
            all_chunks_for_check = chunk_text(content, doc_id=doc_id, kb_id=kb_id)
            total_expected = len(all_chunks_for_check)
            chunk_ids_seen = set()
            for entry in existing_l1:
                chunk_ids_seen.update(entry.get("chunk_ids", []))
            if len(chunk_ids_seen) >= total_expected:
                artifacts = _validate_artifacts(kb_id, doc_id)
                if artifacts["l2_compiled"] and artifacts["l1_compiled"]:
                    _update_compile_detail(doc_id, "l2_compiled")
                    _update_compile_detail(doc_id, "l1_compiled")
                    return {"doc_id": doc_id, "status": "skipped", "l1_results": existing_l1, "chunks": []}
                # Artifacts invalid — fall through to re-compile
                logger.warning(
                    "Document %s marked completed but artifacts invalid in parallel path, re-compiling", doc_id,
                )

    # Load parsed content
    parsed_path = settings.KB_DIR / kb_id / "documents" / doc_id / "parsed.md"
    if not parsed_path.exists():
        return {"doc_id": doc_id, "status": "no_parsed", "l1_results": [], "chunks": []}

    with open(parsed_path, "r", encoding="utf-8") as f:
        content = f.read()

    # L2 compile
    chunks = chunk_text(content, doc_id=doc_id, kb_id=kb_id)
    l2 = L2Compiler(embedding_provider=None)
    l2.save_chunks(chunks, kb_id, doc_id)
    l2.build_fts_index(chunks)
    _update_compile_detail(doc_id, "l2_compiled")

    # L1 compile
    l1 = L1Compiler(llm_client)
    l1_results = await l1.compile_batch(
        chunks,
        batch_size=L1_BATCH_SIZE,
        progress_cb=lambda m: _send_progress(progress_cb, {
            "type": "status",
            "phase": "compiling_l1",
            "message": f"{doc_name}: {m}",
        }),
    )
    l1.save(l1_results, kb_id, doc_id)
    _update_compile_detail(doc_id, "l1_compiled")

    # Mark document as compiled
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE documents SET compile_status = 'completed' WHERE id = ?",
            (doc_id,),
        )
        conn.commit()
    finally:
        conn.close()

    return {"doc_id": doc_id, "status": "ok", "l1_results": l1_results, "chunks": chunks}


@router.post("/{kb_id}")
async def trigger_compilation(kb_id: str, force: bool = False, sample: bool = False, mode: str = "fast"):
    """Trigger full L0/L1/L2 pre-compilation (synchronous, no progress).

    Args:
        mode: L1 compilation mode — "fast" (1 abstract per doc, default),
              "standard" (batch summaries), or "deep" (standard + cross-refs).
        sample: If true, large documents use ~20% chunk sampling.
    """
    # Guard against concurrent compilations
    if kb_id in _active_compilations and not force:
        raise HTTPException(status_code=409, detail="Compilation already in progress for this KB. Use ?force=true to override.")

    # Verify KB exists and get current status
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT id, compile_status FROM knowledge_bases WHERE id = ?", (kb_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        if row["compile_status"] == "processing" and not force:
            raise HTTPException(status_code=409, detail="KB is already being compiled.")
        conn.execute(
            "UPDATE knowledge_bases SET compile_status = 'processing', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (kb_id,),
        )
        conn.commit()
    finally:
        conn.close()

    try:
        result = await run_compilation(kb_id, lambda msg: logger.info("[compile %s] %s", kb_id, msg), sample=sample, l1_mode=mode)

        conn = get_connection()
        try:
            conn.execute(
                "UPDATE knowledge_bases SET compile_status = 'completed', wiki_status = 'pending', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (kb_id,),
            )
            conn.commit()
        finally:
            conn.close()

        return result

    except Exception as e:
        logger.error("Compilation failed for KB %s: %s\n%s", kb_id, e, traceback.format_exc())
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE knowledge_bases SET compile_status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (kb_id,),
            )
            conn.commit()
        finally:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}/status")
async def get_compile_status(kb_id: str):
    """Get compilation status."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT compile_status FROM knowledge_bases WHERE id = ?",
            (kb_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        return {"kb_id": kb_id, "status": row["compile_status"]}
    finally:
        conn.close()


@router.post("/{kb_id}/parallel")
async def trigger_compilation_parallel(kb_id: str, force: bool = False):
    """Trigger L1/L2 compilation with parallel per-document dispatch using SubagentDispatcher."""
    if kb_id in _active_compilations and not force:
        raise HTTPException(status_code=409, detail="Compilation already in progress")

    conn = get_connection()
    try:
        cursor = conn.execute("SELECT id FROM knowledge_bases WHERE id = ?", (kb_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        conn.execute(
            "UPDATE knowledge_bases SET compile_status = 'processing', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (kb_id,),
        )
        conn.commit()
    finally:
        conn.close()

    try:
        db_configs = load_model_configs()
        if not db_configs:
            raise RuntimeError("No model configuration found")
        router_obj = ModelRouter()
        router_obj.register(db_configs)
        llm_client = LLMClient(router_obj)

        doc_conn = get_connection()
        try:
            cursor = doc_conn.execute(
                "SELECT id, filename FROM documents WHERE kb_id = ? AND parse_status = 'completed'",
                (kb_id,),
            )
            docs = cursor.fetchall()
        finally:
            doc_conn.close()

        if not docs:
            raise RuntimeError("No parsed documents found")

        # Use SubagentDispatcher for parallel L1 per document
        dispatcher = SubagentDispatcher(max_concurrency=min(4, len(docs)))
        for doc in docs:
            dispatcher.add_task(
                doc["id"],
                _compile_single_document(
                    kb_id, doc["id"], doc["filename"] or doc["id"],
                    llm_client, lambda msg: logger.info("[parallel compile %s/%s] %s", kb_id, doc["id"], msg),
                ),
            )

        results = await dispatcher.run()
        successful = dispatcher.get_successful()
        all_l1_results = []
        for r in successful:
            if r.result and r.result.get("l1_results"):
                all_l1_results.extend(r.result["l1_results"])

        # L0 compile (needs all L1 results)
        if all_l1_results:
            entity_count, timeline_count = merge_kb_entities(all_l1_results, kb_id)

        conn = get_connection()
        try:
            conn.execute(
                "UPDATE knowledge_bases SET compile_status = 'completed', wiki_status = 'pending', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (kb_id,),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "kb_id": kb_id,
            "status": "completed",
            "documents_processed": len(successful),
            "l1_summaries": len(all_l1_results),
        }

    except Exception as e:
        logger.error("Parallel compilation failed for KB %s: %s\n%s", kb_id, e, traceback.format_exc())
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE knowledge_bases SET compile_status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (kb_id,),
            )
            conn.commit()
        finally:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))


async def _run_subscriber_ws(websocket: WebSocket, kb_id: str, existing: dict):
    """Attach a reconnect WS to an active compilation using a queue.

    Each subscriber gets its own asyncio.Queue. The shared progress_cb puts
    messages into all subscriber queues (no direct WS send). This avoids
    concurrent-write conflicts on the same WebSocket.
    """
    import logging
    logging.info("Compile WS reconnect: %s — subscribing to active compilation", kb_id)

    queue: asyncio.Queue[str] = asyncio.Queue()
    sub_entry = {"ws": websocket, "queue": queue}
    existing["subscribers"].append(sub_entry)

    try:
        # Seed queue with current compile status from DB
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT status, progress, message FROM compile_queue WHERE kb_id = ? ORDER BY started_at DESC LIMIT 1",
                (kb_id,),
            ).fetchone()
        finally:
            conn.close()
        if row:
            await queue.put(json.dumps({
                "type": "progress",
                "progress": row["progress"] or 0,
                "message": row["message"] or "编译进行中...",
            }))
        else:
            await queue.put(json.dumps({
                "type": "progress",
                "progress": 50,
                "message": "编译进行中（重连中）",
            }))

        # Two concurrent tasks: forward queue→WS  and  listen for cancel from client
        async def forward_to_ws():
            while True:
                msg = await queue.get()
                await websocket.send_text(msg)
                try:
                    data = json.loads(msg)
                    if data.get("type") in ("done", "error", "paused"):
                        return
                except (json.JSONDecodeError, KeyError):
                    pass

        async def wait_for_cancel():
            try:
                while True:
                    text = await websocket.receive_text()
                    try:
                        data = json.loads(text)
                        if data.get("type") == "cancel":
                            existing["cancel_event"].set()
                            return
                    except (json.JSONDecodeError, KeyError):
                        pass
            except Exception:
                pass  # WS closed by client

        fwd_task = asyncio.create_task(forward_to_ws())
        cancel_task = asyncio.create_task(wait_for_cancel())
        done, pending = await asyncio.wait(
            [fwd_task, cancel_task], return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
    except Exception as e:
        import logging
        logging.error("Subscriber error for %s: %s", kb_id, e)
    finally:
        try:
            existing["subscribers"].remove(sub_entry)
        except ValueError:
            pass
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/{kb_id}")
async def websocket_compile(websocket: WebSocket, kb_id: str):
    """WebSocket endpoint for compilation progress with cancel support.

    If a compilation is already running for this KB, attaches to it
    instead of starting a new one.

    Uses per-subscriber asyncio.Queue to avoid concurrent WS writes.
    """
    await websocket.accept()

    # If KB already compiled, return result immediately (no re-compile on refresh)
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT compile_status FROM knowledge_bases WHERE id = ?",
            (kb_id,),
        ).fetchone()
    finally:
        conn.close()
    if row and row["compile_status"] == "completed" and kb_id not in _active_compilations:
        try:
            await websocket.send_text(json.dumps({
                "type": "done",
                "progress": 100,
                "message": "编译已完成",
            }))
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
        return

    # Check if compilation is already running — subscribe to existing one
    if kb_id in _active_compilations:
        existing = _active_compilations[kb_id]
        if "subscribers" in existing:
            await _run_subscriber_ws(websocket, kb_id, existing)
            return

    # Verify KB exists
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT id FROM knowledge_bases WHERE id = ?", (kb_id,))
        if not cursor.fetchone():
            await websocket.send_text(json.dumps({"type": "error", "message": "Knowledge base not found"}))
            await websocket.close()
            return
        conn.execute(
            "UPDATE knowledge_bases SET compile_status = 'processing', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (kb_id,),
        )
        conn.commit()
    except Exception as e:
        await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        await websocket.close()
        return
    finally:
        conn.close()

    # Each subscriber: {"ws": WebSocket, "queue": asyncio.Queue}
    cancel_event = asyncio.Event()
    main_queue: asyncio.Queue[str] = asyncio.Queue()
    _subscribers: list[dict] = [{"ws": websocket, "queue": main_queue}]

    async def progress_cb(data: dict):
        msg = json.dumps(data)
        # Put message in all subscriber queues (snapshot to avoid mutation during iteration)
        dead = []
        for sub in list(_subscribers):
            try:
                sub["queue"].put_nowait(msg)
            except asyncio.QueueFull:
                dead.append(sub)
        for sub in dead:
            try:
                _subscribers.remove(sub)
            except ValueError:
                pass
        # Update queue progress in DB
        conn = None
        try:
            conn = get_connection()
            conn.execute(
                "UPDATE compile_queue SET progress = ?, message = ? WHERE id = ?",
                (data.get("progress", 0), data.get("message", ""), queue_id),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

    queue_id = f"cq_{uuid.uuid4().hex[:12]}"
    _active_compilations[kb_id] = {"cancel_event": cancel_event, "subscribers": _subscribers}
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO compile_queue (id, kb_id, status, message) VALUES (?, ?, 'processing', '编译已启动')",
            (queue_id, kb_id),
        )
        conn.commit()
    finally:
        conn.close()

    # Forward messages from main queue to the original WS
    async def main_sender():
        while True:
            msg = await main_queue.get()
            await websocket.send_text(msg)

    # Listen for cancel from the original client
    async def listen_for_cancel():
        try:
            while True:
                text = await websocket.receive_text()
                try:
                    data = json.loads(text)
                    if data.get("type") == "cancel":
                        cancel_event.set()
                        break
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    sender_task = asyncio.create_task(main_sender())
    cancel_task = asyncio.create_task(listen_for_cancel())

    try:
        result = await run_compilation(kb_id, progress_cb, cancel_event=cancel_event)

        conn = get_connection()
        try:
            conn.execute(
                "UPDATE knowledge_bases SET compile_status = 'completed', wiki_status = 'pending', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (kb_id,),
            )
            conn.execute(
                "UPDATE compile_queue SET status = 'completed', progress = 100, message = '编译完成', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (queue_id,),
            )
            conn.commit()
        finally:
            conn.close()

        # Broadcast done via queues
        done_msg = json.dumps({
            "type": "done",
            "progress": 100,
            "message": "编译完成",
            "stats": result,
        })
        for sub in list(_subscribers):
            try:
                sub["queue"].put_nowait(done_msg)
            except asyncio.QueueFull:
                pass
        # Let sender tasks flush the done message
        await asyncio.sleep(0.2)

        # Auto-trigger Wiki generation as background task
        asyncio.create_task(_auto_generate_wiki(kb_id))
    except Exception as e:
        logger.error("WS compilation failed for KB %s: %s\n%s", kb_id, e, traceback.format_exc())
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE knowledge_bases SET compile_status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (kb_id,),
            )
            conn.execute(
                "UPDATE compile_queue SET status = 'failed', error = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (str(e), queue_id),
            )
            conn.commit()
        finally:
            conn.close()

        # Broadcast error via queues
        error_msg = json.dumps({"type": "error", "message": str(e)})
        for sub in list(_subscribers):
            try:
                sub["queue"].put_nowait(error_msg)
            except asyncio.QueueFull:
                pass
        await asyncio.sleep(0.2)
    finally:
        cancel_task.cancel()
        sender_task.cancel()
        _active_compilations.pop(kb_id, None)
        try:
            await websocket.close()
        except Exception:
            pass


@router.post("/{kb_id}/cancel")
async def cancel_compilation(kb_id: str):
    """Cancel an ongoing compilation via HTTP (fallback if WS not available)."""
    if kb_id in _active_compilations:
        _active_compilations[kb_id]["cancel_event"].set()
        return {"kb_id": kb_id, "status": "cancelling"}
    raise HTTPException(status_code=404, detail="No active compilation for this KB")


@router.get("/queue")
async def get_compile_queue(kb_id: str = None):
    """Get compile queue, optionally filtered by KB."""
    conn = get_connection()
    try:
        if kb_id:
            cursor = conn.execute(
                "SELECT * FROM compile_queue WHERE kb_id = ? ORDER BY started_at DESC",
                (kb_id,),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM compile_queue ORDER BY started_at DESC LIMIT 50"
            )
        rows = cursor.fetchall()
        return {"queue": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/{kb_id}/recover")
async def recover_compilation(kb_id: str):
    """Recover interrupted compilation for a KB."""
    conn = get_connection()
    try:
        # Find last interrupted/failed compilation for this KB
        cursor = conn.execute(
            "SELECT * FROM compile_queue WHERE kb_id = ? AND status IN ('processing', 'failed') ORDER BY started_at DESC LIMIT 1",
            (kb_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No interrupted compilation found")

        # Mark as recovered and re-trigger
        conn.execute(
            "UPDATE compile_queue SET status = 'pending', message = '已恢复，等待重新编译', started_at = CURRENT_TIMESTAMP, completed_at = NULL, error = NULL WHERE id = ?",
            (row["id"],),
        )
        conn.commit()
    finally:
        conn.close()

    # Re-trigger compilation via WS-compatible path
    return {
        "kb_id": kb_id,
        "queue_id": row["id"],
        "message": "编译已恢复，请通过 WebSocket 重新连接",
        "ws_url": f"/api/compile/ws/{kb_id}",
    }


async def _auto_generate_wiki(kb_id: str) -> None:
    """Auto-trigger Wiki generation after compilation completes. Runs as background task."""
    try:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE knowledge_bases SET wiki_status = 'generating' WHERE id = ?",
                (kb_id,),
            )
            conn.commit()
        finally:
            conn.close()

        db_configs = load_model_configs()
        if not db_configs:
            logger.warning("Wiki auto-gen skipped: no model config for KB %s", kb_id)
            return

        router_obj = ModelRouter()
        router_obj.register(db_configs)
        llm_client = LLMClient(router_obj)

        from app.services.wiki.lightweight_generator import generate_wiki_lightweight
        await generate_wiki_lightweight(kb_id)

        conn = get_connection()
        try:
            conn.execute(
                "UPDATE knowledge_bases SET wiki_status = 'completed' WHERE id = ?",
                (kb_id,),
            )
            conn.commit()
        finally:
            conn.close()

        logger.info("Wiki auto-generated for KB %s", kb_id)
    except Exception as e:
        logger.error("Wiki auto-gen failed for KB %s: %s", kb_id, e)
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE knowledge_bases SET wiki_status = 'failed' WHERE id = ?",
                (kb_id,),
            )
            conn.commit()
        finally:
            conn.close()


@router.post("/{kb_id}/wiki")
async def trigger_wiki_generation(kb_id: str):
    """Trigger Wiki generation independently (after compilation is done).

    Wiki is no longer part of the main compilation pipeline.
    Call this endpoint after compilation completes to generate Wiki pages.
    """
    # Verify KB exists and is compiled
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT id, compile_status FROM knowledge_bases WHERE id = ?",
            (kb_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        if row["compile_status"] != "completed":
            raise HTTPException(status_code=400, detail="KB must be compiled first before generating Wiki")
    finally:
        conn.close()

    # Check L0 entities exist
    l0_dir = settings.KB_DIR / kb_id / "l0"
    if not (l0_dir / "entities.json").exists():
        raise HTTPException(status_code=400, detail="No entity data found. Run compilation first.")

    try:
        db_configs = load_model_configs()
        if not db_configs:
            raise RuntimeError("No model configuration found")

        router_obj = ModelRouter()
        router_obj.register(db_configs)
        llm_client = LLMClient(router_obj)

        from app.services.wiki.pipeline import WikiPipeline
        pipeline = WikiPipeline(llm_client, kb_id)
        wiki_result = await pipeline.run(progress_cb=lambda _: None)

        return {"kb_id": kb_id, "status": "completed", "result": str(wiki_result)}
    except Exception as e:
        logger.error("Wiki generation failed for KB %s: %s\n%s", kb_id, e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Wiki generation failed: {e}")
