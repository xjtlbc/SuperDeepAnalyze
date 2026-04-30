"""Plain text file parser."""

from pathlib import Path

from app.services.parsing.types import ParsedDocument, DocType
from app.services.parsing.docling_parser import compute_file_hash


class TextParser:
    """Parse plain text files by reading content directly."""

    def parse(self, file_path: Path, doc_id: str, kb_id: str) -> ParsedDocument:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        return ParsedDocument(
            doc_id=doc_id,
            kb_id=kb_id,
            filename=file_path.name,
            content=content,
            file_hash=compute_file_hash(file_path),
            file_type=DocType.TEXT,
            metadata={},
        )
