"""Knowledge base CRUD API."""

import uuid
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.models.database import get_connection

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


class CreateKBRequest(BaseModel):
    name: str
    description: str = ""


class UpdateKBRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class KBResponse(BaseModel):
    id: str
    name: str
    description: str
    compile_status: str
    document_count: int
    created_at: str


@router.get("", response_model=list[KBResponse])
async def list_kbs():
    """List all knowledge bases."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """SELECT kb.id, kb.name, kb.description, kb.compile_status, kb.created_at,
                      COUNT(d.id) as document_count
               FROM knowledge_bases kb
               LEFT JOIN documents d ON kb.id = d.kb_id
               GROUP BY kb.id
               ORDER BY kb.created_at DESC"""
        )
        rows = cursor.fetchall()
        return [
            KBResponse(
                id=row["id"],
                name=row["name"],
                description=row["description"] or "",
                compile_status=row["compile_status"],
                document_count=row["document_count"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
    finally:
        conn.close()


@router.get("/{kb_id}", response_model=KBResponse)
async def get_kb(kb_id: str):
    """Get a single knowledge base."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """SELECT kb.id, kb.name, kb.description, kb.compile_status, kb.created_at,
                      COUNT(d.id) as document_count
               FROM knowledge_bases kb
               LEFT JOIN documents d ON kb.id = d.kb_id
               WHERE kb.id = ?
               GROUP BY kb.id""",
            (kb_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        return KBResponse(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            compile_status=row["compile_status"],
            document_count=row["document_count"],
            created_at=row["created_at"],
        )
    finally:
        conn.close()


@router.post("", response_model=KBResponse, status_code=201)
async def create_kb(data: CreateKBRequest):
    """Create a new knowledge base."""
    if not data.name or not data.name.strip():
        raise HTTPException(status_code=422, detail="Knowledge base name cannot be empty")

    kb_id = f"kb_{uuid.uuid4().hex[:8]}"
    kb_dir = settings.KB_DIR / kb_id
    kb_dir.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO knowledge_bases (id, name, description, compile_status) VALUES (?, ?, ?, ?)",
            (kb_id, data.name, data.description, "pending"),
        )
        conn.commit()
    finally:
        conn.close()

    return KBResponse(
        id=kb_id,
        name=data.name,
        description=data.description,
        compile_status="pending",
        document_count=0,
        created_at=datetime.now().isoformat(),
    )


@router.put("/{kb_id}", response_model=KBResponse)
async def update_kb(kb_id: str, data: UpdateKBRequest):
    """Update a knowledge base name and/or description."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name, description, compile_status, created_at FROM knowledge_bases WHERE id = ?",
            (kb_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        new_name = data.name.strip() if data.name else row["name"]
        new_desc = data.description if data.description is not None else row["description"]

        if not new_name:
            raise HTTPException(status_code=422, detail="Knowledge base name cannot be empty")

        conn.execute(
            "UPDATE knowledge_bases SET name = ?, description = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_name, new_desc, kb_id),
        )
        conn.commit()

        return KBResponse(
            id=row["id"],
            name=new_name,
            description=new_desc or "",
            compile_status=row["compile_status"],
            document_count=0,
            created_at=row["created_at"],
        )
    finally:
        conn.close()


@router.delete("/{kb_id}", status_code=204)
async def delete_kb(kb_id: str):
    """Delete a knowledge base and all its data."""
    conn = get_connection()
    try:
        # Check existence first (Bug #4 fix: return 404 for nonexistent KB)
        exists = conn.execute(
            "SELECT id FROM knowledge_bases WHERE id = ?", (kb_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        conn.execute("BEGIN IMMEDIATE")
        # Delete child tables that reference knowledge_bases (order matters for FK)
        conn.execute("DELETE FROM fts_content WHERE doc_id IN (SELECT id FROM documents WHERE kb_id = ?)", (kb_id,))
        conn.execute("DELETE FROM messages WHERE session_id IN (SELECT id FROM sessions WHERE kb_id = ?)", (kb_id,))
        conn.execute("DELETE FROM sessions WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM documents WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM entities WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM timeline_events WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM wiki_catalog WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM wiki_pages WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM wiki_analysis WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM compile_queue WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM kb_memory WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM precompile_cache WHERE doc_id IN (SELECT id FROM documents WHERE kb_id = ?)", (kb_id,))
        # Finally the parent row
        conn.execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Delete from filesystem
    kb_dir = settings.KB_DIR / kb_id
    if kb_dir.exists():
        import shutil
        shutil.rmtree(str(kb_dir), ignore_errors=True)

    # Delete FAISS indexes
    faiss_dir = settings.FAISS_DIR / kb_id
    if faiss_dir.exists():
        import shutil
        shutil.rmtree(str(faiss_dir), ignore_errors=True)

    return None
