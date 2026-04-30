"""Two-stage wiki analysis: structured extraction with quality gates."""

from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.config import settings
from app.models.config import RoleType


@dataclass
class ExtractionStats:
    """Quality metrics from the extraction stage."""
    entity_count: int = 0
    relation_count: int = 0
    contradiction_count: int = 0
    avg_entity_confidence: float = 0.0
    entities_with_relations: int = 0
    isolated_entity_count: int = 0
    high_severity_contradictions: int = 0

    def is_valid(self) -> bool:
        """Quality gate: must have minimum data to generate a meaningful report."""
        if self.entity_count < 3:
            return False
        if self.relation_count < 1:
            return False
        if self.avg_entity_confidence < 0.3:
            return False
        return True


class AnalysisExtractor:
    """Stage 1: Extract structured data from L0/L1/L2 with quality gates.

    Unlike the reAct-based AnalysisAgent, this is a two-pass structured
    extraction: first pass extracts entities and relations from each L1
    summary batch in parallel, second pass extracts contradictions and
    narrative threads from the aggregated results.
    """

    def __init__(self, llm_client, kb_id: str):
        self._llm_client = llm_client
        self._kb_id = kb_id

    async def run(self, progress_cb=None) -> tuple[dict, ExtractionStats]:
        """Run extraction pipeline.

        Returns:
            (extracted_data, stats) where extracted_data is a dict with
            keys: entities, relations, contradictions, concepts, gaps, threads
        """
        if progress_cb:
            await _cb(progress_cb, {"phase": "extraction", "message": "正在读取L0数据..."})

        l0_data = self._load_l0_data()

        if progress_cb:
            await _cb(progress_cb, {"phase": "extraction", "message": "正在读取L1摘要..."})

        l1_batches = self._load_l1_summaries()
        if not l1_batches:
            if progress_cb:
                await _cb(progress_cb, {"phase": "extraction", "message": "警告: 未找到L1摘要数据"})

        # Stage 1a: Extract entities + relations from each L1 batch
        if progress_cb:
            await _cb(progress_cb, {
                "phase": "extraction",
                "message": f"正在从 {len(l1_batches)} 批摘要中提取实体和关系...",
            })

        all_entities: list[dict] = l0_data.get("entities", [])
        all_relations: list[dict] = l0_data.get("relations", [])
        all_concepts: list[dict] = []

        # Extract from L1 summaries
        for i, (doc_id, summaries) in enumerate(l1_batches):
            if progress_cb:
                await _cb(progress_cb, {
                    "phase": "extraction",
                    "message": f"提取文档 {doc_id[:8]}... ({i+1}/{len(l1_batches)})",
                })

            result = await self._extract_entities_relations(doc_id, summaries)
            all_entities.extend(result.get("entities", []))
            all_relations.extend(result.get("relations", []))
            all_concepts.extend(result.get("concepts", []))

        # Deduplicate entities by name
        all_entities = self._deduplicate_entities(all_entities)

        # Assign sequential IDs
        all_entities = self._assign_entity_ids(all_entities)

        # Stage 1b: Extract contradictions and threads from aggregated data
        if progress_cb:
            await _cb(progress_cb, {"phase": "extraction", "message": "正在提取矛盾点和叙事线索..."})

        contradictions = await self._extract_contradictions(all_entities, all_relations, l1_batches)
        threads = await self._extract_threads(all_entities, all_relations, l0_data.get("timeline", []))

        # Stage 1c: Extract knowledge gaps
        gaps = self._find_gaps(all_entities, all_relations)

        extracted = {
            "entities": all_entities,
            "relations": all_relations,
            "contradictions": contradictions,
            "concepts": all_concepts,
            "gaps": gaps,
            "threads": threads,
        }

        stats = self._compute_stats(extracted)

        if progress_cb:
            await _cb(progress_cb, {
                "phase": "extraction",
                "message": (
                    f"提取完成: {stats.entity_count} 实体, {stats.relation_count} 关系, "
                    f"{stats.contradiction_count} 矛盾, 平均置信度 {stats.avg_entity_confidence:.2f}"
                ),
            })

        return extracted, stats

    # --- L0/L1 data loading ---

    def _load_l0_data(self) -> dict:
        """Load L0 entities, timeline, cross_refs, relations, and event_graph."""
        l0_dir = settings.KB_DIR / self._kb_id / "l0"
        result = {
            "entities": [],
            "timeline": [],
            "cross_refs": [],
            "relations": [],
            "event_graph": {},
        }

        for key, filename in [
            ("entities", "entities.json"),
            ("timeline", "timeline.json"),
            ("cross_refs", "cross_refs.json"),
            ("relations", "relations.json"),
            ("event_graph", "event_graph.json"),
        ]:
            path = l0_dir / filename
            if path.exists():
                try:
                    result[key] = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    pass
        return result

    def _load_l1_summaries(self) -> list[tuple[str, list[dict]]]:
        """Load L1 summaries for all documents. Returns [(doc_id, summaries), ...]."""
        l1_dir = settings.KB_DIR / self._kb_id / "documents"
        if not l1_dir.exists():
            return []

        batches = []
        for doc_dir in sorted(l1_dir.iterdir()):
            l1_path = doc_dir / "l1_summaries.json"
            if l1_path.exists():
                try:
                    summaries = json.loads(l1_path.read_text(encoding="utf-8"))
                    batches.append((doc_dir.name, summaries))
                except Exception:
                    pass
        return batches

    # --- LLM extraction calls ---

    async def _extract_entities_relations(self, doc_id: str, summaries: list[dict]) -> dict:
        """Extract entities and relations from one document's L1 summaries."""
        # Build context from summaries (limit to avoid token overflow)
        context_parts = []
        total_chars = 0
        max_chars = 8000

        for s in summaries:
            chunk_summary = s.get("summary", "")
            if total_chars + len(chunk_summary) > max_chars:
                break
            chunk_ids = ", ".join(str(c) for c in s.get("chunk_ids", [])[:5])
            context_parts.append(f"[chunks: {chunk_ids}]\n{chunk_summary}")
            total_chars += len(chunk_summary)

        context = "\n\n---\n\n".join(context_parts)

        from app.services.prompts.domain import detect_kb_domain, get_domain_config
        domain = detect_kb_domain(self._kb_id)
        cfg = get_domain_config(domain)

        system_prompt = f"""你是一个{cfg['material']}信息提取专家。从给定文本中提取：
1. **实体**：{cfg['entity_types']}
2. **关系**：实体间的关系，需附原文证据
3. **概念**：抽象概念和关键术语

以JSON格式返回，格式为：
{{
  "entities": [{{"name": "", "type": "person|organization|location|event|concept|method|model|dataset|metric", "aliases": [], "attributes": {{}}, "importance": 0.5, "confidence": 0.8}}],
  "relations": [{{"source": "", "target": "", "relation_type": "", "evidence": "", "confidence": 0.8}}],
  "concepts": [{{"name": "", "description": ""}}]
}}

只返回JSON，不要其他内容。"""

        user_prompt = f"从以下文本中提取实体、关系和概念：\n\n{context}"

        response = await self._llm_client.chat(
            role=RoleType.MAIN,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.2,
        )

        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Parse JSON from response
        try:
            # Try direct parse first
            result = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from code block or text
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    result = json.loads(content[start:end])
                except json.JSONDecodeError:
                    result = {"entities": [], "relations": [], "concepts": []}
            else:
                result = {"entities": [], "relations": [], "concepts": []}

        # Add doc_id as source to all items
        for e in result.get("entities", []):
            e["source_doc"] = doc_id
        for r in result.get("relations", []):
            r["source_doc"] = doc_id
        for c in result.get("concepts", []):
            c["source_doc"] = doc_id

        return result

    async def _extract_contradictions(self, entities: list[dict], relations: list[dict], l1_batches: list) -> list[dict]:
        """Extract contradictions by analyzing cross-document inconsistencies."""
        # Build summary of entities that appear in multiple docs with conflicting info
        entity_docs: dict[str, list] = {}
        for e in entities:
            name = e.get("name", "")
            doc = e.get("source_doc", "")
            if name and doc:
                if name not in entity_docs:
                    entity_docs[name] = []
                entity_docs[name].append({"doc": doc, "type": e.get("type"), "attributes": e.get("attributes", {})})

        # Only analyze entities appearing in multiple docs
        multi_doc_entities = {k: v for k, v in entity_docs.items() if len(v) > 1}
        if not multi_doc_entities:
            return []

        context = json.dumps(multi_doc_entities, ensure_ascii=False)[:6000]

        system_prompt = """分析以下在不同文档中出现的实体信息，找出可能的矛盾点或不一致之处。
以JSON数组返回，格式为：
[{"type": "time_conflict|statement_conflict|evidence_conflict|logical_gap", "description": "", "involved_entities": [], "severity": "high|medium|low"}]

只返回JSON数组，不要其他内容。"""

        user_prompt = f"以下实体在不同文档中出现，请找出矛盾或不一致之处：\n\n{context}"

        try:
            response = await self._llm_client.chat(
                role=RoleType.MAIN,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.2,
            )
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            try:
                result = json.loads(content)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                start = content.find("[")
                end = content.rfind("]") + 1
                if start >= 0 and end > start:
                    try:
                        return json.loads(content[start:end])
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

        return []

    async def _extract_threads(self, entities: list[dict], relations: list[dict], timeline: list[dict]) -> list[dict]:
        """Extract narrative threads from entities, relations, and timeline."""
        if not entities:
            return []

        # Summarize key entities and relations
        entity_summary = json.dumps([{"name": e["name"], "type": e.get("type")} for e in entities[:30]], ensure_ascii=False)
        rel_summary = json.dumps([{"source": r["source"], "target": r["target"], "type": r["relation_type"]} for r in relations[:30]], ensure_ascii=False)
        time_summary = json.dumps([{"time": t.get("time"), "desc": t.get("description")} for t in timeline[:20]], ensure_ascii=False)

        context = f"实体: {entity_summary}\n\n关系: {rel_summary}\n\n时间线: {time_summary}"

        system_prompt = """基于以下实体、关系和时间线信息，识别主要的叙事线索（案件主线、副线）。
以JSON数组返回，格式为：
[{"title": "", "description": "", "key_entities": [], "timeline_events": [], "type": "main|subplot"}]

只返回JSON数组，不要其他内容。"""

        user_prompt = f"请从以下信息中识别叙事线索：\n\n{context}"

        try:
            response = await self._llm_client.chat(
                role=RoleType.MAIN,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.2,
            )
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            try:
                result = json.loads(content)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                start = content.find("[")
                end = content.rfind("]") + 1
                if start >= 0 and end > start:
                    try:
                        return json.loads(content[start:end])
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

        return []

    # --- Post-processing ---

    def _deduplicate_entities(self, entities: list[dict]) -> list[dict]:
        """Deduplicate entities by name (case-insensitive). Merge attributes."""
        seen: dict[str, dict] = {}
        for e in entities:
            name = e.get("name", "").strip().lower()
            if not name:
                continue
            if name in seen:
                # Merge: keep higher importance, merge aliases and attributes
                existing = seen[name]
                if e.get("importance", 0) > existing.get("importance", 0):
                    existing["importance"] = e["importance"]
                existing_aliases = set(existing.get("aliases", []))
                existing_aliases.update(e.get("aliases", []))
                existing["aliases"] = list(existing_aliases)
                existing.get("attributes", {}).update(e.get("attributes", {}))
                # Track source docs
                if "source_docs" not in existing:
                    existing["source_docs"] = [existing.get("source_doc", "")]
                if e.get("source_doc") and e["source_doc"] not in existing["source_docs"]:
                    existing["source_docs"].append(e["source_doc"])
            else:
                seen[name] = {
                    "name": e.get("name", ""),  # Keep original case
                    "type": e.get("type", "person"),
                    "aliases": e.get("aliases", []),
                    "attributes": e.get("attributes", {}),
                    "importance": e.get("importance", 0.5),
                    "confidence": e.get("confidence", 0.8),
                    "source_doc": e.get("source_doc", ""),
                    "source_docs": [e.get("source_doc", "")] if e.get("source_doc") else [],
                }

        return list(seen.values())

    def _assign_entity_ids(self, entities: list[dict]) -> list[dict]:
        """Assign sequential IDs to deduplicated entities."""
        for i, e in enumerate(entities, 1):
            e["id"] = f"entity_{i:04d}"
        return entities

    def _find_gaps(self, entities: list[dict], relations: list[dict]) -> list[dict]:
        """Find knowledge gaps: isolated entities, missing info."""
        # Find entities with no relations
        entity_names_in_relations = set()
        for r in relations:
            entity_names_in_relations.add(r.get("source", "").lower())
            entity_names_in_relations.add(r.get("target", "").lower())

        gaps = []
        for e in entities:
            name = e.get("name", "").lower()
            if name and name not in entity_names_in_relations:
                gaps.append({
                    "description": f"实体 {e['name']} 未与其他实体建立关系，可能遗漏关键关联",
                    "type": "isolated_entity",
                    "suggestion": f"进一步搜索 {e['name']} 的相关信息",
                    "related_entity_id": e.get("id"),
                })

        # Find entities with low confidence
        for e in entities:
            if e.get("confidence", 1.0) < 0.4:
                gaps.append({
                    "description": f"实体 {e['name']} 置信度较低 ({e.get('confidence', 0):.2f})，建议人工核实",
                    "type": "unanswered_question",
                    "suggestion": "需要更多来源佐证",
                    "related_entity_id": e.get("id"),
                })

        return gaps

    def _compute_stats(self, extracted: dict) -> ExtractionStats:
        """Compute quality metrics from extracted data."""
        entities = extracted.get("entities", [])
        relations = extracted.get("relations", [])
        contradictions = extracted.get("contradictions", [])

        # Entity relation coverage
        entity_names_in_relations: set[str] = set()
        for r in relations:
            entity_names_in_relations.add(r.get("source", "").lower())
            entity_names_in_relations.add(r.get("target", "").lower())

        entities_with_relations = sum(
            1 for e in entities if e.get("name", "").lower() in entity_names_in_relations
        )

        avg_confidence = 0.0
        if entities:
            confs = [e.get("confidence", 0.5) for e in entities]
            avg_confidence = sum(confs) / len(confs)

        return ExtractionStats(
            entity_count=len(entities),
            relation_count=len(relations),
            contradiction_count=len(contradictions),
            avg_entity_confidence=avg_confidence,
            entities_with_relations=entities_with_relations,
            isolated_entity_count=len(entities) - entities_with_relations,
            high_severity_contradictions=sum(
                1 for c in contradictions if c.get("severity") == "high"
            ),
        )


async def _cb(cb, data: dict):
    result = cb(data)
    if asyncio.iscoroutine(result):
        await result
