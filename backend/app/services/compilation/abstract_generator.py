"""L0 Abstract Generator: lightweight ~125-token document abstracts.

Called after L1 compilation. Each document gets a compact abstract
that allows the Agent to quickly assess relevance without reading
the full document.

Enhanced with: key numbers extraction, legal document type detection,
legal references, and cross-document entity inference.
"""
import json
import re
from pathlib import Path

from app.config import settings, flags
from app.models.config import RoleType
from app.utils.logging_config import get_logger

logger = get_logger("app.compilation.abstract")

_ABSTRACT_PROMPT = (
    "请用以下格式概括文档内容（总计不超过150个token）：\n"
    "主题: [一句话主题]\n"
    "要点: [2-3个核心要点，用分号分隔]\n"
    "关键实体: [最多5个人名/组织名/地点，用逗号分隔]\n"
    "关键数字: [金额、数量、百分比等数字信息，无则写'无']\n"
    "法条引用: [文档中引用的法律条款，无则写'无']\n"
    "文档类型: [起诉书/判决书/裁定书/证人证言/讯问笔录/鉴定报告/银行流水/合同协议/其他]\n\n"
    "文档摘要内容：\n{content}"
)

# Known legal document type patterns (Chinese legal system)
_DOC_TYPE_PATTERNS: list[tuple[str, list[str]]] = [
    ("起诉书", ["起诉书", "公诉", "指控", "被告人"]),
    ("判决书", ["判决书", "判决如下", "裁定如下", "本院认为"]),
    ("裁定书", ["裁定书", "裁定"]),
    ("证人证言", ["证人", "证言", "证明", "作证"]),
    ("讯问笔录", ["讯问", "笔录", "问:", "答:", "犯罪嫌疑人"]),
    ("鉴定报告", ["鉴定", "鉴定意见", "检验", "司法鉴定"]),
    ("银行流水", ["银行", "流水", "账户", "交易记录", "转账"]),
    ("合同协议", ["合同", "协议", "甲方", "乙方"]),
]

# Legal article reference patterns
_LEGAL_REF_PATTERNS = [
    re.compile(r"《([^》]+)》\s*第\s*(\d+)\s*条"),
    re.compile(r"第\s*(\d+)\s*条\s*之"),
    re.compile(r"刑法\s*第\s*(\d+)\s*条"),
    re.compile(r"刑事诉讼法\s*第\s*(\d+)\s*条"),
]

# Monetary/number patterns
_NUMBER_PATTERNS = [
    re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:万|亿)?\s*(?:元|美元|人民币)"),
    re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*笔"),
    re.compile(r"共计?\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:元|万|亿)"),
]


async def generate_doc_abstract(
    llm_client,
    l1_summaries: list[dict],
    doc_name: str = "",
) -> dict:
    """Generate a compact abstract from L1 summaries.

    Enhanced with: key numbers, legal document type auto-detection,
    legal references extraction, and cross-entity inference.
    """
    if not flags.compile_abstract_enhancement:
        # Fallback to simple abstract generation (original logic)
        return await _generate_simple_abstract(llm_client, l1_summaries, doc_name)

    content_parts = []
    all_text = ""
    for s in l1_summaries[:5]:
        summary_text = s.get("summary", "")
        if summary_text:
            content_parts.append(summary_text[:600])
            all_text += summary_text + "\n"
    combined = "\n\n".join(content_parts)
    if not combined.strip():
        combined = doc_name or "未知文档"

    prompt = _ABSTRACT_PROMPT.format(content=combined[:2500])
    abstract = ""
    try:
        response = await llm_client.chat(
            role=RoleType.LIGHTWEIGHT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        abstract = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        logger.warning("Abstract generation failed for %s: %s", doc_name, e)

    if not abstract or len(abstract) < 10:
        first_summary = l1_summaries[0].get("summary", "") if l1_summaries else ""
        abstract = first_summary[:200] + "..." if first_summary else f"[文档: {doc_name}]"

    # ── Enhanced field extraction ──────────────────────────────────
    entities_top5 = []
    for s in l1_summaries:
        entities = s.get("entities_mentioned", [])
        entities_top5.extend(entities)
    entities_top5 = list(dict.fromkeys(entities_top5))[:5]

    # Also parse entities from the abstract's "关键实体:" line
    import re
    ent_match = re.search(r'关键实体[：:]\s*(.+)', abstract)
    if ent_match:
        raw_ents = ent_match.group(1).strip()
        # Split by comma / Chinese comma / semicolon
        parsed = [e.strip() for e in re.split(r'[,，;；、]', raw_ents) if e.strip()]
        for e in parsed:
            # Skip generic/empty entries
            if len(e) >= 2 and e not in ('无', '暂无', '未提及'):
                entities_top5.append(e)
    entities_top5 = list(dict.fromkeys(entities_top5))[:10]

    # Auto-detect document type from content patterns
    doc_type = _detect_doc_type(all_text, doc_name)

    # Extract legal references
    legal_refs = _extract_legal_refs(all_text + abstract)

    # Extract key numbers (amounts, counts, percentages)
    key_numbers = _extract_key_numbers(all_text)

    # Infer related documents via entity overlap
    related_docs = _infer_related_docs(entities_top5, doc_name)

    token_count = _estimate_tokens(abstract)

    return {
        "abstract": abstract.strip(),
        "token_count": token_count,
        "entities_top5": entities_top5,
        "key_entities": entities_top5,  # backward compat with compile.py
        "doc_type": doc_type,
        "key_numbers": key_numbers,
        "legal_references": legal_refs,
        "related_documents": related_docs,
    }


def _detect_doc_type(text: str, filename: str) -> str:
    """Auto-detect legal document type from content and filename."""
    combined = text + filename
    for doc_type, keywords in _DOC_TYPE_PATTERNS:
        score = sum(1 for kw in keywords if kw in combined)
        if score >= 2:
            return doc_type
    return "其他"


def _extract_legal_refs(text: str) -> list[str]:
    """Extract legal article references from text."""
    refs: set[str] = set()
    for pat in _LEGAL_REF_PATTERNS:
        for m in pat.findall(text):
            if isinstance(m, tuple):
                refs.add("".join(m))
            else:
                refs.add(m)
    return sorted(refs)[:10]


def _extract_key_numbers(text: str) -> list[dict]:
    """Extract key numeric information (amounts, counts, percentages)."""
    numbers = []
    for pat in _NUMBER_PATTERNS:
        for m in pat.finditer(text):
            val = m.group(0).strip()
            # Find surrounding context
            start = max(0, m.start() - 30)
            end = min(len(text), m.end() + 30)
            ctx = text[start:end].replace("\n", " ").strip()
            numbers.append({"value": val, "context": ctx})
    return numbers[:10]


def _infer_related_docs(entities: list[dict], current_doc: str) -> list[str]:
    """Infer related documents by entity overlap (placeholder)."""
    # This is a lightweight heuristic — full cross-doc inference
    # happens in the contradiction detector and entity merger.
    return []  # Populated at the KB level by entity_merger


async def _generate_simple_abstract(llm_client, l1_summaries, doc_name: str) -> dict:
    """Original simple abstract generation (used when feature flag is off)."""
    content_parts = []
    for s in l1_summaries[:3]:
        summary_text = s.get("summary", "")
        if summary_text:
            content_parts.append(summary_text[:600])
    combined = "\n\n".join(content_parts)
    if not combined.strip():
        combined = doc_name or "未知文档"

    simple_prompt = (
        "请用以下格式概括文档内容（总计不超过125个token）：\n"
        "主题: [一句话主题]\n"
        "要点: [2-3个核心要点，用分号分隔]\n"
        "关键实体: [最多5个人名/组织名/地点，用逗号分隔]\n"
        "文档类型: [报告/笔录/账目/合同/鉴定/其他]\n\n"
        f"文档摘要内容：\n{combined[:2000]}"
    )

    abstract = ""
    try:
        response = await llm_client.chat(
            role=RoleType.LIGHTWEIGHT,
            messages=[{"role": "user", "content": simple_prompt}],
            temperature=0.2,
        )
        abstract = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception:
        pass

    if not abstract or len(abstract) < 10:
        first_summary = l1_summaries[0].get("summary", "") if l1_summaries else ""
        abstract = first_summary[:200] + "..." if first_summary else f"[文档: {doc_name}]"

    entities_top5 = list(dict.fromkeys(
        s.get("entities_mentioned", []) for s in l1_summaries
    ))[:5]

    return {
        "abstract": abstract.strip(),
        "token_count": _estimate_tokens(abstract),
        "entities_top5": entities_top5,
        "doc_type": "其他",
    }


def save_abstract(abstract_data: dict, kb_id: str, doc_id: str) -> Path:
    """Save a single document's abstract to filesystem."""
    doc_dir = settings.KB_DIR / kb_id / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    path = doc_dir / "doc_abstract.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(abstract_data, f, ensure_ascii=False, indent=2)
    return path


def collect_all_abstracts(kb_id: str) -> list[dict]:
    """Collect all document abstracts for a KB into a single list.

    Scans each document directory for doc_abstract.json files.
    """
    abstracts = []
    kb_dir = settings.KB_DIR / kb_id / "documents"
    if not kb_dir.exists():
        return abstracts

    for doc_dir in sorted(kb_dir.iterdir()):
        if not doc_dir.is_dir():
            continue
        abstract_path = doc_dir / "doc_abstract.json"
        if abstract_path.exists():
            try:
                data = json.loads(abstract_path.read_text(encoding="utf-8"))
                data["doc_id"] = doc_dir.name
                abstracts.append(data)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read abstract for %s: %s", doc_dir.name, e)

    return abstracts


def save_all_abstracts(abstracts: list[dict], kb_id: str) -> Path:
    """Save the combined abstracts index to l0/doc_abstracts.json."""
    l0_dir = settings.KB_DIR / kb_id / "l0"
    l0_dir.mkdir(parents=True, exist_ok=True)
    path = l0_dir / "doc_abstracts.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(abstracts, f, ensure_ascii=False, indent=2)
    return path


def _estimate_tokens(text: str) -> int:
    """CJK-aware token estimation."""
    cjk_count = sum(1 for c in text if '一' <= c <= '鿿')
    ascii_count = len(text) - cjk_count
    return int(cjk_count * 1.8 + ascii_count * 0.25)
