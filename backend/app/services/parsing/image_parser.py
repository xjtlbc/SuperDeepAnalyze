"""Image parser using VLM OCR."""

from pathlib import Path

from app.services.parsing.types import DocType, ParsedDocument
from app.services.parsing.docling_parser import compute_file_hash
from app.services.parsing.vlm_ocr import VLMOCRParser


class ImageParser:
    """Parse images (JPG/PNG/WebP) using VLM OCR."""

    def __init__(self, vlm_config):
        self._vlm = VLMOCRParser(vlm_config)

    async def parse(self, file_path: str | Path, doc_id: str, kb_id: str) -> ParsedDocument:
        return await self._vlm.parse_image(file_path, doc_id, kb_id)
