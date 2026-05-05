"""Hybrid retrieval engine: vector search + FTS5 keyword search + RRF fusion."""

import json
import re
from app.models.database import get_connection
from app.services.retrieval.faiss_index import FAISSIndexManager
from app.services.agent.retrieval_engine.confidence import (
    ConfidenceLevel,
    add_confidence_to_results,
)
from app.services.agent.retrieval_engine.rrf import (
    RRFConfig,
    reciprocal_rank_fusion,
)

# Chinese grammar particles and stopwords to strip from search queries
_CJK_PARTICLES = set("的了是在和与或就着过们这那个一不也有会被从到把给向让")
_CJK_STOPWORDS = {
    "什么", "怎么", "为什么", "如何", "哪里", "哪个", "这个", "那些",
    "怎样", "多少", "几个", "是否", "能否", "可以", "还是", "一个",
    "一些", "什么", "起来", "出来", "下去", "过来", "回来",
    "关于", "对于", "根据", "按照", "通过", "需要", "已经", "可以",
    "应该", "可能", "没有", "不是", "或者", "而且", "因为", "所以",
}

# Try to import jieba for proper Chinese segmentation
_HAS_JIEBA = False
try:
    import jieba
    _HAS_JIEBA = True
except ImportError:
    pass


def _extract_chinese_words(text: str) -> list[str]:
    """Extract meaningful search words from Chinese text.

    Strategy:
    1. If jieba available: use jieba.cut_for_search for proper segmentation
    2. Else try rewrite_query for entity extraction
    3. Else: regex n-gram extraction
    """
    # Strategy 1: jieba segmentation (best quality)
    if _HAS_JIEBA:
        clean = re.sub(r'[][？?！!。，,、；;：:""''（）()【】\n\r\t]', ' ', text)
        clean = re.sub(r'\s+', ' ', clean).strip()
        if clean:
            words = [w for w in jieba.cut_for_search(clean)
                     if len(w) >= 2 and w not in _CJK_STOPWORDS
                     and not all(c in _CJK_PARTICLES for c in w)]
            if words:
                return list(dict.fromkeys(words))[:8]

    # Strategy 2: rewrite_query entity extraction
    try:
        from app.services.retrieval.query_rewriter import rewrite_query
        rewritten = rewrite_query(text)
        words = list(rewritten.entities) if rewritten.entities else []
        for sq in rewritten.sub_queries[:3]:
            for w in sq.split():
                if len(w) >= 2 and w not in _CJK_STOPWORDS:
                    words.append(w)
        if words:
            return list(dict.fromkeys(words))[:8]
    except Exception:
        pass

    # Strategy 3: regex n-gram extraction
    clean = re.sub(r'[][？?！!。，,、；;：:""''（）()【】\n\r\t]', ' ', text)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if not clean:
        return []

    words = []
    segments = clean.split()
    for seg in segments:
        if not seg:
            continue
        is_cjk = all('一' <= c <= '鿿' or c in _CJK_PARTICLES for c in seg)
        if is_cjk:
            stripped = "".join(c for c in seg if c not in _CJK_PARTICLES)
            for n in (4, 3, 2):
                i = 0
                while i <= len(stripped) - n:
                    w = stripped[i:i + n]
                    if w not in _CJK_STOPWORDS:
                        words.append(w)
                    i += n
        else:
            if len(seg) >= 2:
                words.append(seg)

    return list(dict.fromkeys(w for w in words if w not in _CJK_STOPWORDS))[:8]


class KeywordSearch:
    """SQLite FTS5 keyword search."""

    @staticmethod
    def search(query: str, doc_id: str | None = None, top_k: int = 10, kb_id: str | None = None) -> list[dict]:
        """Search FTS5 index for keyword matches."""
        # Strip punctuation and special chars that break FTS5 MATCH
        import re
        clean = re.sub(r'[][？?！!。，,、；;：:""''（）()【】\n\r\t]', ' ', query)
        clean = re.sub(r'\s+', ' ', clean).strip()
        if not clean:
            return []
        conn = get_connection()
        try:
            if kb_id:
                # Filter by kb_id via documents table join
                if doc_id:
                    cursor = conn.execute(
                        """SELECT f.doc_id, f.chunk_id, f.content, f.rank
                           FROM fts_content f
                           JOIN documents d ON f.doc_id = d.id
                           WHERE fts_content MATCH ? AND f.doc_id = ? AND d.kb_id = ?
                           ORDER BY rank
                           LIMIT ?""",
                        (clean, doc_id, kb_id, top_k),
                    )
                else:
                    cursor = conn.execute(
                        """SELECT f.doc_id, f.chunk_id, f.content, f.rank
                           FROM fts_content f
                           JOIN documents d ON f.doc_id = d.id
                           WHERE fts_content MATCH ? AND d.kb_id = ?
                           ORDER BY rank
                           LIMIT ?""",
                        (clean, kb_id, top_k),
                    )
            else:
                if doc_id:
                    cursor = conn.execute(
                        """SELECT doc_id, chunk_id, content, rank
                           FROM fts_content
                           WHERE fts_content MATCH ? AND doc_id = ?
                           ORDER BY rank
                           LIMIT ?""",
                        (clean, doc_id, top_k),
                    )
                else:
                    cursor = conn.execute(
                        """SELECT doc_id, chunk_id, content, rank
                           FROM fts_content
                           WHERE fts_content MATCH ?
                           ORDER BY rank
                           LIMIT ?""",
                        (clean, top_k),
                    )
            rows = cursor.fetchall()

            # FTS5 unicode61 tokenizer splits Chinese character-by-character,
            # so multi-char words like "案件" or "被告" match 0 rows.
            # Fall back to LIKE when FTS returns nothing and kb_id is set.
            if not rows and kb_id:
                words = _extract_chinese_words(clean)
                if words:
                    # Use OR: any word match counts as a hit
                    like_clauses = ["f.content LIKE ?" for _ in words]
                    like_params = [f"%{w}%" for w in words]
                    where_extra = " OR ".join(like_clauses)
                    if doc_id:
                        cursor = conn.execute(
                            f"""SELECT f.doc_id, f.chunk_id, f.content, 0 AS rank
                                FROM fts_content f
                                JOIN documents d ON f.doc_id = d.id
                                WHERE ({where_extra}) AND f.doc_id = ? AND d.kb_id = ?
                                LIMIT ?""",
                            like_params + [doc_id, kb_id, top_k],
                        )
                    else:
                        cursor = conn.execute(
                            f"""SELECT f.doc_id, f.chunk_id, f.content, 0 AS rank
                                FROM fts_content f
                                JOIN documents d ON f.doc_id = d.id
                                WHERE ({where_extra}) AND d.kb_id = ?
                                LIMIT ?""",
                            like_params + [kb_id, top_k],
                        )
                    rows = cursor.fetchall()

            return [
                {
                    "doc_id": row["doc_id"],
                    "chunk_id": row["chunk_id"],
                    "content": row["content"][:200],
                    "score": row["rank"],
                }
                for row in rows
            ]
        finally:
            conn.close()


def rrf_merge(results_a: list[dict], results_b: list[dict], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion: merge two ranked result lists."""
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}

    for rank, item in enumerate(results_a, 1):
        key = f"{item['doc_id']}:{item.get('chunk_id', '')}"
        scores[key] = scores.get(key, 0) + 1 / (k + rank)
        items[key] = item

    for rank, item in enumerate(results_b, 1):
        key = f"{item['doc_id']}:{item.get('chunk_id', '')}"
        scores[key] = scores.get(key, 0) + 1 / (k + rank)
        if key not in items:
            items[key] = item

    # Sort by RRF score descending
    merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [items[key] | {"rrf_score": score} for key, score in merged]


async def hybrid_search(
    query: str,
    kb_id: str,
    top_k: int = 10,
    rrf_k: int = 60,
    doc_id: str | None = None,
    add_confidence: bool = True,
    embedding_provider=None,
) -> list[dict]:
    """Combined hybrid search: vector + keyword + RRF fusion.

    Args:
        query: Search query string
        kb_id: Knowledge base ID
        top_k: Number of results to return
        rrf_k: RRF constant parameter
        doc_id: Optional document ID to limit search scope
        add_confidence: Whether to add confidence labels to results
        embedding_provider: Optional LLM client for computing query embeddings

    Returns:
        Merged and ranked search results with confidence levels
    """
    # Vector search
    vec_results = []
    if embedding_provider is not None:
        try:
            query_embedding = await embedding_provider.embed([query])
            if query_embedding:
                faiss_mgr = FAISSIndexManager()
                index = faiss_mgr.load_index(kb_id, "l2")
                if index is not None:
                    vec_results_raw = faiss_mgr.search(kb_id, "l2", query_embedding[0], top_k=top_k * 2)
                    if vec_results_raw:
                        vec_results = vec_results_raw
        except Exception as e:
            import logging
            logging.getLogger("app.retrieval.hybrid_search").warning("Vector search failed: %s", e)

    # Keyword search
    kw_results = KeywordSearch.search(query, doc_id=doc_id, top_k=top_k * 2, kb_id=kb_id)

    # RRF merge (when both results available)
    merged = rrf_merge(vec_results, kw_results, k=rrf_k)

    # Add confidence labels if requested
    if add_confidence:
        merged = add_confidence_to_results(merged, source="hybrid")

    return merged[:top_k]


def hybrid_search_with_graph(
    query: str,
    kb_id: str,
    vector_results: list[dict] | None = None,
    keyword_results: list[dict] | None = None,
    graph_results: list[dict] | None = None,
    config: RRFConfig | None = None,
    add_confidence: bool = True,
) -> list[dict]:
    """Enhanced hybrid search with graph results integration.

    Args:
        query: Search query string (for keyword search if not provided)
        kb_id: Knowledge base ID
        vector_results: Pre-computed vector search results
        keyword_results: Pre-computed keyword search results
        graph_results: Pre-computed graph search results
        config: RRF configuration
        add_confidence: Whether to add confidence labels

    Returns:
        Merged and ranked results with confidence levels
    """
    if config is None:
        config = RRFConfig()

    # Perform keyword search if results not provided
    if keyword_results is None and query:
        keyword_results = KeywordSearch.search(query, top_k=config.top_k * 2, kb_id=kb_id)

    # Merge using RRF
    merged = reciprocal_rank_fusion(
        vector_results=vector_results or [],
        keyword_results=keyword_results or [],
        graph_results=graph_results,
        config=config,
    )

    # Add confidence labels
    if add_confidence:
        merged = add_confidence_to_results(merged, source="hybrid")

    return merged
