from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class DocType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    CSV = "csv"
    IMAGE = "image"
    TEXT = "text"


@dataclass
class Chunk:
    """A chunk of text with metadata."""
    chunk_id: str
    doc_id: str
    kb_id: str
    content: str
    token_count: int = 0
    page_range: list[int] = field(default_factory=list)
    paragraph_range: list[int] = field(default_factory=list)
    file_hash: str = ""
    is_overlap: bool = False


@dataclass
class ParsedDocument:
    """Unified parsed document output from any parser."""
    doc_id: str
    kb_id: str
    filename: str
    file_type: DocType
    file_hash: str
    content: str          # Structured Markdown
    metadata: dict = field(default_factory=dict)
