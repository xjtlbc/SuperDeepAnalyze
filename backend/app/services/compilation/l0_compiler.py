"""L0 compiler: global entity library, timeline, event graph, and cross-references."""

import asyncio
import json
import uuid
from pathlib import Path

from app.config import settings
from app.models.config import RoleType
from app.models.database import get_connection


class L0Compiler:
    """Compile L0 layer: global entities, timeline, event graph, cross-refs."""

    def __init__(self, llm_client):
        self._llm_client = llm_client

    async def compile(self, all_l1_summaries: list[dict], kb_id: str) -> dict:
        """Build global L0 structures from all L1 summaries."""
        # Format L1 summaries for L0 prompt
        summaries_text = self._format_l1_summaries(all_l1_summaries)

        # Call main LLM for global analysis (with timeout + retry)
        max_retries = 3
        result = None
        for attempt in range(max_retries):
            try:
                result = await asyncio.wait_for(
                    self._llm_client.build_l0(summaries_text, kb_id=kb_id),
                    timeout=600,
                )
                break
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    import logging
                    logging.warning("L0 compile timeout (attempt %d/%d), retrying...", attempt + 1, max_retries)
                else:
                    raise RuntimeError(f"L0 编译超时（{max_retries} 次重试后仍失败），请检查模型 API 响应速度")

        # Process and normalize results
        l0_data = self._normalize_l0_result(result, kb_id)

        # Quality gate: validate L0 output before saving
        quality = self._quality_check(l0_data, len(all_l1_summaries))
        l0_data["quality"] = quality

        # Save to filesystem
        self._save_l0(l0_data, kb_id)

        # Save to database
        self._save_to_db(l0_data, kb_id)

        return l0_data

    def _format_l1_summaries(self, summaries: list[dict]) -> str:
        """Format L1 summaries into a single text for L0 processing."""
        parts = []
        for i, summary in enumerate(summaries):
            parts.append(f"## Batch {i + 1}")
            parts.append(f"**Chunks:** {', '.join(summary.get('chunk_ids', []))}")
            parts.append(f"**Summary:** {summary.get('summary', '')}")
            if summary.get("relations"):
                rels = [f"{r['from']}-{r['to']}({r['type']})" for r in summary["relations"]]
                parts.append(f"**Relations:** {', '.join(rels)}")
            if summary.get("contradictions"):
                parts.append(f"**Contradictions:**")
                for c in summary["contradictions"]:
                    parts.append(f"  - {c.get('description', '')}")
            parts.append("")
        return "\n".join(parts)

    def _normalize_l0_result(self, raw: dict, kb_id: str) -> dict:
        """Normalize L0 output with proper IDs and structure."""
        entities = []
        entity_name_to_id = {}

        for i, entity in enumerate(raw.get("entities", [])):
            entity_id = f"entity_{kb_id}_{i + 1:03d}"
            entity_name_to_id[entity.get("name", "")] = entity_id
            entities.append({
                "id": entity_id,
                "name": entity.get("name", ""),
                "type": entity.get("type", "unknown"),
                "aliases": entity.get("aliases", []),
                "attributes": entity.get("attributes", {}),
                "mentions": entity.get("mentions", []),
            })

        # Build timeline with entity ID references
        timeline = []
        for i, event in enumerate(raw.get("timeline", [])):
            participant_ids = []
            for p in event.get("participants", []):
                if p in entity_name_to_id:
                    participant_ids.append(entity_name_to_id[p])
            timeline.append({
                "id": f"event_{kb_id}_{i + 1:03d}",
                "time": event.get("time", ""),
                "description": event.get("description", ""),
                "participants": participant_ids,
                "source_refs": event.get("source_refs", []),
            })

        # Build event graph
        event_graph = {
            "nodes": [e["id"] for e in timeline],
            "edges": raw.get("event_graph", {}).get("edges", []),
        }

        return {
            "kb_id": kb_id,
            "entities": entities,
            "timeline": timeline,
            "event_graph": event_graph,
            "cross_refs": raw.get("cross_refs", []),
        }

    def _save_l0(self, l0_data: dict, kb_id: str) -> None:
        """Save L0 data to filesystem."""
        l0_dir = settings.KB_DIR / kb_id / "l0"
        l0_dir.mkdir(parents=True, exist_ok=True)

        with open(l0_dir / "entities.json", "w", encoding="utf-8") as f:
            json.dump(l0_data["entities"], f, ensure_ascii=False, indent=2)
        with open(l0_dir / "timeline.json", "w", encoding="utf-8") as f:
            json.dump(l0_data["timeline"], f, ensure_ascii=False, indent=2)
        with open(l0_dir / "event_graph.json", "w", encoding="utf-8") as f:
            json.dump(l0_data["event_graph"], f, ensure_ascii=False, indent=2)
        with open(l0_dir / "cross_refs.json", "w", encoding="utf-8") as f:
            json.dump(l0_data["cross_refs"], f, ensure_ascii=False, indent=2)

    def _save_to_db(self, l0_data: dict, kb_id: str) -> None:
        """Save L0 data to SQLite database."""
        conn = get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")

            # Ensure KB record exists (foreign key requirement)
            conn.execute(
                "INSERT OR IGNORE INTO knowledge_bases (id, name, compile_status) VALUES (?, ?, ?)",
                (kb_id, f"KB {kb_id}", "completed"),
            )

            # Save entities
            for entity in l0_data["entities"]:
                conn.execute(
                    """INSERT OR REPLACE INTO entities
                       (id, kb_id, name, entity_type, aliases, attributes, mentions)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entity["id"], kb_id, entity["name"], entity["type"],
                        json.dumps(entity.get("aliases", []), ensure_ascii=False),
                        json.dumps(entity.get("attributes", {}), ensure_ascii=False),
                        json.dumps(entity.get("mentions", []), ensure_ascii=False),
                    ),
                )

            # Save timeline events
            for event in l0_data["timeline"]:
                conn.execute(
                    """INSERT OR REPLACE INTO timeline_events
                       (id, kb_id, event_time, description, participants, source_refs)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        event["id"], kb_id, event.get("time", ""),
                        event.get("description", ""),
                        json.dumps(event.get("participants", []), ensure_ascii=False),
                        json.dumps(event.get("source_refs", []), ensure_ascii=False),
                    ),
                )

            conn.commit()
        finally:
            conn.close()

    def _quality_check(self, l0_data: dict, l1_batch_count: int) -> dict:
        """Validate L0 compilation quality before saving."""
        issues = []
        entities = l0_data.get("entities", [])
        timeline = l0_data.get("timeline", [])
        event_graph = l0_data.get("event_graph", {})
        relations_count = sum(len(e.get("relations", [])) for e in entities)

        # Check: entities should not be empty
        if not entities:
            issues.append("no_entities")
        elif len(entities) < 2 and l1_batch_count > 5:
            issues.append("too_few_entities")

        # Check: entities should not be abnormally many
        if len(entities) > l1_batch_count * 50:
            issues.append("too_many_entities")

        # Check: timeline should exist for case documents
        if not timeline and l1_batch_count > 3:
            issues.append("empty_timeline")

        # Check: relations should exist
        if relations_count == 0 and len(entities) > 1:
            issues.append("no_relations")

        # Check: event graph should have nodes
        graph_nodes = len(event_graph.get("nodes", []))
        if graph_nodes == 0 and l1_batch_count > 3:
            issues.append("empty_event_graph")

        status = "pass" if not issues else "needs_review"

        return {
            "status": status,
            "issues": issues,
            "entity_count": len(entities),
            "timeline_count": len(timeline),
            "relation_count": relations_count,
            "graph_node_count": graph_nodes,
            "l1_batch_count": l1_batch_count,
        }
