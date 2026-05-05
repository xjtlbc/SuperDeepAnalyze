"""Batch expand API: efficient multi-document retrieval endpoints."""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.models.database import get_connection

router = APIRouter(prefix="/api/expand", tags=["expand"])


class SummaryRequest(BaseModel):
    doc_ids: list[str]


class SectionRequest(BaseModel):
    doc_id: str
    section_indices: list[int] | None = None


@router.get("/{kb_id}/abstracts")
async def get_abstracts(kb_id: str):
    """Return all document abstracts for a KB in one query."""
    l0_dir = settings.KB_DIR / kb_id / "l0"
    abstracts_path = l0_dir / "doc_abstracts.json"

    if abstracts_path.exists():
        data = json.loads(abstracts_path.read_text(encoding="utf-8"))
        return {"abstracts": data, "count": len(data)}

    # Fallback: scan individual doc_abstract.json files
    from app.services.compilation.abstract_generator import collect_all_abstracts
    abstracts = collect_all_abstracts(kb_id)
    if not abstracts:
        return {"abstracts": [], "count": 0}

    return {"abstracts": abstracts, "count": len(abstracts)}


@router.post("/{kb_id}/summaries")
async def get_summaries(kb_id: str, req: SummaryRequest):
    """Return L1 summaries for specified documents."""
    if not req.doc_ids:
        raise HTTPException(400, "doc_ids is required")

    results = []
    for doc_id in req.doc_ids:
        l1_path = settings.KB_DIR / kb_id / "documents" / doc_id / "l1_summaries.json"
        if l1_path.exists():
            summaries = json.loads(l1_path.read_text(encoding="utf-8"))
            results.append({
                "doc_id": doc_id,
                "summary_count": len(summaries),
                "summaries": summaries[:10],  # Cap at 10 sections per doc
            })
        else:
            results.append({"doc_id": doc_id, "summary_count": 0, "summaries": []})

    return {"results": results}


@router.post("/{kb_id}/sections")
async def get_sections(kb_id: str, req: SectionRequest):
    """Return specific L1 summary sections for a document."""
    l1_path = settings.KB_DIR / kb_id / "documents" / req.doc_id / "l1_summaries.json"
    if not l1_path.exists():
        raise HTTPException(404, f"No L1 summaries for {req.doc_id}")

    summaries = json.loads(l1_path.read_text(encoding="utf-8"))
    if req.section_indices:
        selected = [summaries[i] for i in req.section_indices if 0 <= i < len(summaries)]
    else:
        selected = summaries

    return {"doc_id": req.doc_id, "sections": selected, "total": len(summaries)}
