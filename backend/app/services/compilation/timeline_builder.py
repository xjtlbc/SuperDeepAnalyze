"""Enhanced timeline builder for legal case analysis.

Extracts dates from both L2 raw text and L1 summaries, resolves relative
dates, associates events with entities, and produces a structured timeline.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from app.config import settings, flags

logger = logging.getLogger("app.compilation.timeline")

# Date patterns: absolute + relative Chinese dates
_ABSOLUTE_PATTERNS = [
    re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]"),
    re.compile(r"(\d{4})[年\-./](\d{1,2})[月\-./](\d{1,2})"),
    re.compile(r"(\d{4})\s*年(?!.{0,6}(?:出生|[诞產]生|[出诞]生于))[\s\S]{0,6}?(\d{1,2})\s*月"),
    re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})"),
    re.compile(r"(20\d{2})\.(\d{1,2})\.(\d{1,2})"),
]

_RELATIVE_PATTERNS = [
    re.compile(r"(\d+)\s*天\s*[后前]"),
    re.compile(r"(\d+)\s*[个]?\s*月\s*[后前]"),
    re.compile(r"(\d+)\s*[个]?\s*[周年]\s*[后前]"),
    re.compile(r"[次翌]日"),
    re.compile(r"当[天日]"),
]


def _parse_absolute_date(text: str) -> list[tuple[str, int]]:
    """Extract absolute dates from text. Returns [(date_str, char_position)]."""
    results = []
    for pat in _ABSOLUTE_PATTERNS:
        for m in pat.finditer(text):
            groups = m.groups()
            if len(groups) >= 3:
                try:
                    y, mo, d = int(groups[0]), int(groups[1]), int(groups[2])
                    if 1900 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                        date_str = f"{y}-{mo:02d}-{d:02d}"
                        results.append((date_str, m.start()))
                except (ValueError, IndexError):
                    pass
            elif len(groups) == 2:
                try:
                    y, mo = int(groups[0]), int(groups[1])
                    if 1900 <= y <= 2100 and 1 <= mo <= 12:
                        date_str = f"{y}-{mo:02d}"
                        results.append((date_str, m.start()))
                except (ValueError, IndexError):
                    pass
    return results


def _resolve_relative_date(base_date: str, rel_text: str) -> str | None:
    """Try to compute an absolute date from a relative expression."""
    try:
        base = datetime.strptime(base_date[:10], "%Y-%m-%d")
    except ValueError:
        return None

    for pat in _RELATIVE_PATTERNS:
        m = pat.search(rel_text)
        if not m:
            continue
        groups = m.groups()
        if m.group(0) in ("次日", "翌日"):
            return (base + timedelta(days=1)).strftime("%Y-%m-%d")
        if m.group(0) == "当天" or m.group(0) == "当日":
            return base.strftime("%Y-%m-%d")
        if groups and groups[0]:
            n = int(groups[0])
            if "月" in m.group(0):
                if "后" in m.group(0):
                    return (base + timedelta(days=n * 30)).strftime("%Y-%m-%d")
                else:
                    return (base - timedelta(days=n * 30)).strftime("%Y-%m-%d")
            elif "年" in m.group(0) or "周" in m.group(0):
                if "后" in m.group(0):
                    return (base + timedelta(days=n * 365)).strftime("%Y-%m-%d")
                else:
                    return (base - timedelta(days=n * 365)).strftime("%Y-%m-%d")
            else:
                if "后" in m.group(0):
                    return (base + timedelta(days=n)).strftime("%Y-%m-%d")
                else:
                    return (base - timedelta(days=n)).strftime("%Y-%m-%d")
    return None


def _load_l2_chunks(kb_id: str) -> list[dict]:
    """Collect all L2 chunk texts for a KB."""
    docs_dir = settings.KB_DIR / kb_id / "documents"
    if not docs_dir.exists():
        return []

    chunks = []
    for doc_dir in docs_dir.iterdir():
        l2_dir = doc_dir / "l2_chunks"
        if not l2_dir.exists():
            continue
        for chunk_file in sorted(l2_dir.glob("*.md")):
            try:
                text = chunk_file.read_text(encoding="utf-8")
                chunks.append({
                    "chunk_id": chunk_file.stem,
                    "doc_id": doc_dir.name,
                    "content": text,
                })
            except Exception:
                pass
    return chunks


def _load_entities(kb_id: str) -> dict[str, dict]:
    """Load entity id → {name, type} mapping."""
    entities_path = settings.KB_DIR / kb_id / "l0" / "entities.json"
    if not entities_path.exists():
        return {}
    with open(entities_path, "r", encoding="utf-8") as f:
        entities = json.load(f)
    return {
        e["id"]: {"name": e["name"], "type": e.get("type", "unknown")}
        for e in entities if isinstance(e, dict) and "id" in e
    }


def _extract_title(description: str, max_len: int = 50) -> str:
    """Extract a short title from a description, filtering metadata artifacts."""
    if not description:
        return "未知事件"
    # Strip common L2 chunk metadata artifacts
    clean = description
    for artifact in ['**Is Overlap:**', 'Token Count:**', '---', '```']:
        idx = clean.find(artifact)
        if idx >= 0:
            # Try to get text after the artifact
            after = clean[idx + len(artifact):].strip()
            if len(after) > 10:
                clean = after
    # Try to find a key action verb pattern
    action_patterns = [
        r'(对[^，。；\n]+(?:进行|作出|实施|依法))',
        r'([^，。；\n]*(?:拘留|逮捕|立案|判决|起诉|通知|认定|查明|核实|调取|冻结|扣押|询问|讯问|侦查|鉴定|批准|决定)[^，。；\n]*)',
        r'([^，。；\n]*?(?:公安局|检察院|法院|分局|派出所|鉴定中心)[^，。；\n]*?(?:对|将|依法|决定)[^，。；\n]*)',
    ]
    for pat in action_patterns:
        m = re.search(pat, clean)
        if m:
            title = m.group(1).strip()
            # Filter out metadata noise
            title = re.sub(r'\*{1,3}|\bToken\s*Count\b|Is\s*Overlap', '', title).strip()
            if 5 <= len(title) <= max_len:
                return title
    # Fallback: first N chars, stripping metadata
    clean = clean.replace('\n', ' ').strip()
    clean = re.sub(r'\*{1,3}\s*(Token Count|Is Overlap)[^*]+\*{1,3}', '', clean)
    clean = re.sub(r'\s{2,}', ' ', clean)
    if len(clean) <= max_len:
        return clean
    return clean[:max_len].rsplit(' ', 1)[0] + '...'


def build_timeline(kb_id: str, l1_results: list[dict] | None = None) -> list[dict]:
    """Build an enhanced timeline from L2 text and L1 summaries.

    Returns sorted timeline events with entity association and confidence scores.
    """
    if not flags.compile_timeline_builder:
        return []

    events: list[dict] = []
    seen: set[str] = set()

    # Phase 1: Extract from L2 raw text
    l2_chunks = _load_l2_chunks(kb_id)
    entity_map = _load_entities(kb_id)

    for chunk in l2_chunks:
        dates = _parse_absolute_date(chunk["content"])
        for date_str, pos in dates:
            # Extract surrounding context (100 chars before/after the date)
            start = max(0, pos - 100)
            end = min(len(chunk["content"]), pos + 100)
            context = chunk["content"][start:end].replace("\n", " ").strip()

            # Find entity mentions in context
            participants = []
            for ent_id, ent_info in entity_map.items():
                if ent_info["name"] in context:
                    participants.append({
                        "id": ent_id,
                        "name": ent_info["name"],
                        "type": ent_info["type"],
                    })

            dedup_key = f"{date_str}|{context[:60]}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            events.append({
                "date": date_str,
                "title": _extract_title(context),
                "description": context[:200],
                "participants": participants[:5],
                "source_docs": [chunk["doc_id"]],
                "source_chunks": [chunk["chunk_id"]],
                "confidence": 0.6,
                "source": "l2_text",
            })

    # Phase 2: Extract from L1 summaries (higher confidence)
    if l1_results:
        for l1 in l1_results:
            summary = l1.get("summary", "")
            dates = _parse_absolute_date(summary)
            for date_str, _ in dates:
                dedup_key = f"{date_str}|{summary[:60]}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                participants = []
                for e in l1.get("entities_mentioned", []):
                    name = e.get("name", "") if isinstance(e, dict) else str(e)
                    for ent_id, ent_info in entity_map.items():
                        if ent_info["name"] == name:
                            participants.append({
                                "id": ent_id,
                                "name": ent_info["name"],
                                "type": ent_info["type"],
                            })
                            break

                events.append({
                    "date": date_str,
                    "title": _extract_title(summary),
                    "description": summary[:200],
                    "participants": participants[:5],
                    "source_docs": [],
                    "source_chunks": l1.get("chunk_ids", [])[:3],
                    "confidence": 0.8,
                    "source": "l1_summary",
                })

    # Phase 3: Resolve relative dates
    events_sorted = sorted(events, key=lambda e: e["date"])
    for i, evt in enumerate(events_sorted):
        context = evt["description"]
        for j in range(max(0, i - 3), i):
            prev_date = events_sorted[j]["date"]
            resolved = _resolve_relative_date(prev_date, context)
            if resolved:
                evt["date"] = resolved
                evt["confidence"] = max(0.5, evt.get("confidence", 0.6) - 0.2)
                evt["inferred_from"] = prev_date
                break

    # Phase 4: Deduplicate by date + similar description
    final_events: list[dict] = []
    for evt in events_sorted:
        dup = False
        for fe in final_events:
            if fe["date"] == evt["date"] and fe["description"][:50] == evt["description"][:50]:
                fe["participants"].extend(evt["participants"])
                fe["source_docs"].extend(evt["source_docs"])
                fe["confidence"] = max(fe["confidence"], evt["confidence"])
                dup = True
                break
        if not dup:
            final_events.append(evt)

    # Save
    l0_dir = settings.KB_DIR / kb_id / "l0"
    l0_dir.mkdir(parents=True, exist_ok=True)
    with open(l0_dir / "timeline.json", "w", encoding="utf-8") as f:
        json.dump(final_events, f, ensure_ascii=False, indent=2)

    logger.info("Timeline build for KB %s: %d events", kb_id, len(final_events))
    return final_events
