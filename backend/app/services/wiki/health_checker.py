"""Wiki Health Checker — detects quality issues in generated wiki content."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings

# Regex to match [[Target]] or [[Target|Display]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]")


def _normalize_wikilink_target(target: str) -> str:
    """Normalize a wikilink target to match page storage naming.

    Page filenames use safe_name = catalog_path.replace('/', '_').replace('\\', '_')
    so we apply the same transform for matching.
    """
    return target.strip().replace("/", "_").replace("\\", "_")


@dataclass
class WikiHealthReport:
    """Result of a full wiki health check."""

    kb_id: str
    orphan_pages: list[dict] = field(default_factory=list)
    sparse_communities: list[dict] = field(default_factory=list)
    broken_links: list[dict] = field(default_factory=list)
    missing_relations: list[dict] = field(default_factory=list)
    total_pages: int = 0
    total_entities: int = 0
    score: float = 1.0


class WikiHealthChecker:
    """Checks a knowledge base's generated wiki for quality issues.

    Usage::

        checker = WikiHealthChecker()
        report = checker.run_full_check("my-kb-id")
        print(f"Health score: {report.score:.2f}")
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pages_dir(self, kb_id: str) -> Path:
        return settings.KB_DIR / kb_id / "wiki" / "pages"

    def _entities_path(self, kb_id: str) -> Path:
        return settings.KB_DIR / kb_id / "l0" / "entities.json"

    def _load_entities(self, kb_id: str) -> list[dict]:
        path = self._entities_path(kb_id)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_page_stems(self, kb_id: str) -> set[str]:
        """Return the set of page safe-names (file stems) for a KB."""
        pages_dir = self._pages_dir(kb_id)
        if not pages_dir.exists():
            return set()
        return {f.stem for f in pages_dir.glob("*.md")}

    def _load_page_paths(self, kb_id: str) -> list[Path]:
        """Return list of absolute paths to every .md page file."""
        pages_dir = self._pages_dir(kb_id)
        if not pages_dir.exists():
            return []
        return sorted(pages_dir.glob("*.md"))

    @staticmethod
    def _parse_wikilinks(markdown_text: str) -> list[str]:
        """Extract bare target names from a markdown string's wikilinks."""
        return _WIKILINK_RE.findall(markdown_text)

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def check_orphan_pages(self, kb_id: str) -> list[dict]:
        """Find pages with zero incoming AND zero outgoing wikilinks.

        Returns a list of dicts with keys: *path*, *title*.
        """
        pages_dir = self._pages_dir(kb_id)
        if not pages_dir.exists():
            return []

        page_files = sorted(pages_dir.glob("*.md"))
        if not page_files:
            return []

        # First pass: collect outgoing links per page
        outgoing: dict[str, set[str]] = {}   # stem -> set of linked stems
        page_meta: dict[str, str] = {}        # stem -> title

        for fp in page_files:
            stem = fp.stem
            try:
                text = fp.read_text(encoding="utf-8")
            except Exception:
                continue

            title = stem
            body = text
            if text.startswith("---"):
                try:
                    end = text.index("---", 3)
                    import yaml
                    fm = yaml.safe_load(text[3:end]) or {}
                    title = fm.get("title", stem)
                    body = text[end + 3:]
                except (ValueError, Exception):
                    pass

            targets = self._parse_wikilinks(body)
            outgoing[stem] = {_normalize_wikilink_target(t) for t in targets}
            page_meta[stem] = title

        # Second pass: compute incoming links (reverse index)
        incoming: dict[str, set[str]] = {stem: set() for stem in page_meta}
        for source, targets in outgoing.items():
            for t in targets:
                if t in incoming:
                    incoming[t].add(source)

        # Identify orphans: no outgoing AND no incoming
        orphans: list[dict] = []
        for stem in page_meta:
            out_count = len(outgoing.get(stem, set()))
            in_count = len(incoming.get(stem, set()))
            if out_count == 0 and in_count == 0:
                orphans.append({
                    "path": stem,
                    "title": page_meta[stem],
                })

        return orphans

    def check_sparse_communities(
        self, kb_id: str, min_nodes: int = 3
    ) -> list[dict]:
        """Find entity types with fewer than *min_nodes* members.

        Returns a list of dicts with keys: *type*, *count*, *min_nodes*.
        """
        entities = self._load_entities(kb_id)
        if not entities:
            return []

        type_counts: dict[str, int] = {}
        for e in entities:
            t = e.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        sparse = [
            {"type": t, "count": c, "min_nodes": min_nodes}
            for t, c in type_counts.items()
            if c < min_nodes
        ]
        return sparse

    def check_broken_links(self, kb_id: str) -> list[dict]:
        """Find wikilinks whose target does not match any existing page.

        Returns a list of dicts with keys: *source_page*, *target*, *line* (1-indexed).
        """
        pages_dir = self._pages_dir(kb_id)
        if not pages_dir.exists():
            return []

        existing_stems = self._load_page_stems(kb_id)

        broken: list[dict] = []
        for fp in sorted(pages_dir.glob("*.md")):
            try:
                lines = fp.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue

            stem = fp.stem
            for line_no, line_text in enumerate(lines, start=1):
                for match in _WIKILINK_RE.finditer(line_text):
                    raw_target = match.group(1).strip()
                    normalized = _normalize_wikilink_target(raw_target)
                    # Also try the raw target as-is
                    if normalized not in existing_stems and raw_target not in existing_stems:
                        broken.append({
                            "source_page": stem,
                            "target": raw_target,
                            "line": line_no,
                        })

        return broken

    def check_missing_relations(self, kb_id: str) -> list[dict]:
        """Find entities that have no relations.

        Returns a list of dicts with keys: *id*, *name*, *type*.
        """
        entities = self._load_entities(kb_id)
        missing: list[dict] = []
        for e in entities:
            relations = e.get("relations", [])
            if not relations:
                missing.append({
                    "id": e["id"],
                    "name": e["name"],
                    "type": e.get("type", "unknown"),
                })
        return missing

    # ------------------------------------------------------------------
    # Full check
    # ------------------------------------------------------------------

    def run_full_check(self, kb_id: str) -> WikiHealthReport:
        """Run all health checks and return a scored report."""
        orphan_pages = self.check_orphan_pages(kb_id)
        sparse_communities = self.check_sparse_communities(kb_id)
        broken_links = self.check_broken_links(kb_id)
        missing_relations = self.check_missing_relations(kb_id)

        total_pages = len(self._load_page_stems(kb_id))
        total_entities = len(self._load_entities(kb_id))

        # Score: start at 1.0 and deduct per issue
        score = 1.0
        score -= len(orphan_pages) * 0.05
        score -= len(sparse_communities) * 0.03
        score -= len(broken_links) * 0.08
        score -= len(missing_relations) * 0.02
        score = max(score, 0.0)

        return WikiHealthReport(
            kb_id=kb_id,
            orphan_pages=orphan_pages,
            sparse_communities=sparse_communities,
            broken_links=broken_links,
            missing_relations=missing_relations,
            total_pages=total_pages,
            total_entities=total_entities,
            score=round(score, 4),
        )
