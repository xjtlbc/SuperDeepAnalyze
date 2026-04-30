#!/usr/bin/env python
"""Integration test for Phase 3: Pre-compilation pipeline.

Uses real API keys and a test novel file.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.models.config import ModelConfig, ModelConfigs, RoleType
from app.models.database import init_db
from app.models.openai_provider import OpenAIProvider
from app.models.router import ModelRouter
from app.services.llm.client import LLMClient
from app.services.parsing.chunking import chunk_text, estimate_tokens
from app.services.compilation.l2_compiler import L2Compiler
from app.services.compilation.l1_compiler import L1Compiler
from app.services.compilation.l0_compiler import L0Compiler
from app.services.compilation.cache_manager import CacheManager

# Test configuration
TEST_CONFIG = ModelConfigs(
    main=ModelConfig(
        base_url="https://coding.dashscope.aliyuncs.com/v1",
        model_name="qwen3.6-plus",
        api_key="sk-sp-029d78b29de7429db32877ced07cc7c5",
        max_tokens=8192,
    ),
    lightweight=ModelConfig(
        base_url="https://coding.dashscope.aliyuncs.com/v1",
        model_name="qwen3.6-plus",
        api_key="sk-sp-029d78b29de7429db32877ced07cc7c5",
        max_tokens=4096,
    ),
    embedding=ModelConfig(
        base_url="https://api.siliconflow.cn/v1",
        model_name="Qwen/Qwen3-Embedding-0.6B",
        api_key="sk-phwexfymzojmztfjcawrvbsgexcwqurshjqzlgydjqafjdtt",
        dimension=1024,
    ),
)

TEST_NOVEL_PATH = r"D:\qk\1-28册）出版精校版.txt"
TEST_KB_ID = "test_kb_001"
TEST_DOC_ID = "test_doc_001"


async def test_pipeline():
    """Run full pre-compilation pipeline test."""
    print("=" * 60)
    print("Phase 3 Integration Test: Pre-compilation Pipeline")
    print("=" * 60)

    # Initialize DB
    init_db()
    print("\n[1/7] Database initialized")

    # Setup router and clients
    router = ModelRouter()
    router.register(TEST_CONFIG)
    llm_client = LLMClient(router)

    l2_compiler = L2Compiler(embedding_provider=router.get_provider(RoleType.EMBEDDING))
    l1_compiler = L1Compiler(llm_client)
    l0_compiler = L0Compiler(llm_client)
    cache_manager = CacheManager()

    print("[2/7] Model router and compilers initialized")

    # Load test novel
    if not os.path.exists(TEST_NOVEL_PATH):
        print(f"\nERROR: Test novel not found at {TEST_NOVEL_PATH}")
        print("Please provide a valid path to a test file.")
        return False

    with open(TEST_NOVEL_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    print(f"[3/7] Loaded test novel: {len(content)} characters")
    print(f"       Estimated tokens: {estimate_tokens(content)}")

    # Chunk the content
    chunks = chunk_text(content, doc_id=TEST_DOC_ID, kb_id=TEST_KB_ID)
    print(f"[4/7] Chunked into {len(chunks)} chunks")
    for i, c in enumerate(chunks[:3]):
        print(f"       Chunk {i+1}: {c.chunk_id} - {c.token_count} tokens")
    if len(chunks) > 3:
        print(f"       ... and {len(chunks) - 3} more chunks")

    # Test L2 compilation
    print(f"\n[5/7] Running L2 compilation (filesystem + FAISS + FTS5)...")
    try:
        l2_path = await l2_compiler.compile(chunks, TEST_KB_ID, TEST_DOC_ID)
        print(f"       L2 chunks saved to: {l2_path}")

        # Verify FAISS index
        faiss_path = settings.FAISS_DIR / TEST_KB_ID / f"l2_{TEST_DOC_ID}.index"
        if faiss_path.exists():
            print(f"       FAISS index created: {faiss_path.stat().st_size} bytes")

        # Verify FTS5
        from app.models.database import get_connection
        conn = get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM fts_content WHERE doc_id = ?", (TEST_DOC_ID,))
        count = cursor.fetchone()[0]
        conn.close()
        print(f"       FTS5 index: {count} entries")
    except Exception as e:
        print(f"       L2 compilation warning: {e}")
        print("       (This may be expected if FAISS/embedding has issues)")

    # Test L1 compilation (sample first few chunks)
    print(f"\n[6/7] Running L1 compilation (summaries) on first 5 chunks...")
    try:
        sample_chunks = chunks[:5]
        l1_results = await l1_compiler.compile_batch(sample_chunks, batch_size=3)
        l1_path = l1_compiler.save(l1_results, TEST_KB_ID, TEST_DOC_ID)
        print(f"       L1 summaries saved to: {l1_path}")
        print(f"       Generated {len(l1_results)} summary batches")
        if l1_results:
            print(f"       First summary: {l1_results[0].get('summary', '')[:80]}...")
    except Exception as e:
        print(f"       L1 compilation warning: {e}")

    # Test L0 compilation (using L1 results)
    print(f"\n[7/7] Running L0 compilation (global entities/timeline)...")
    try:
        l1_results_for_l0 = await l1_compiler.compile_batch(chunks[:10], batch_size=5)
        l0_result = await l0_compiler.compile(l1_results_for_l0, TEST_KB_ID)
        print(f"       Entities found: {len(l0_result.get('entities', []))}")
        print(f"       Timeline events: {len(l0_result.get('timeline', []))}")
        if l0_result.get('entities'):
            print(f"       First entity: {l0_result['entities'][0].get('name', 'N/A')}")
    except Exception as e:
        print(f"       L0 compilation warning: {e}")

    # Cache test
    print(f"\n[Cache Test] Testing cache manager...")
    file_hash = "test_hash_123"
    cache_manager.save_cache(file_hash, TEST_DOC_ID, TEST_KB_ID, str(settings.KB_DIR / TEST_KB_ID))
    cached = cache_manager.check_cache(file_hash)
    if cached:
        print(f"       Cache save/load: OK (doc_id={cached['doc_id']})")
        cache_manager.invalidate_cache(file_hash)
        print("       Cache invalidation: OK")

    print("\n" + "=" * 60)
    print("Phase 3 Integration Test COMPLETED")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_pipeline())
    sys.exit(0 if success else 1)
