"""Dispatch document parsing based on file type.

PDF parsing uses a three-tier fallback strategy:
  1. Docling (layout model + table structure) — best quality, needs models
  2. PyMuPDF direct text extraction — fast fallback, no models needed
  3. VLM multimodal OCR — for scanned/image-heavy PDFs, slow but handles everything
"""

import asyncio
import json
import logging
from pathlib import Path

from app.services.parsing.types import DocType, ParsedDocument
from app.services.parsing.docling_parser import DoclingParser, compute_file_hash
from app.services.parsing.vlm_ocr import VLMOCRParser
from app.services.parsing.docx_parser import DocxParser
from app.services.parsing.excel_parser import ExcelParser
from app.services.parsing.image_parser import ImageParser
from app.services.parsing.text_parser import TextParser
from app.services.parsing.doc_converter import extract_text_from_doc

logger = logging.getLogger("app.parsing")

# Supported extensions
PDF_EXTS = {".pdf"}
DOC_EXTS = {".doc"}
DOCX_EXTS = {".docx"}
XLSX_EXTS = {".xlsx", ".xls", ".csv"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
TEXT_EXTS = {".txt", ".md"}

# PDF routing thresholds
TEXT_DENSITY_VERY_HIGH = 2000  # chars/page → PyMuPDF directly (pure text, no layout analysis needed)
TEXT_DENSITY_HIGH = 500        # chars/page → Docling fast mode (tables/charts may exist)
TEXT_DENSITY_LOW = 100         # chars/page → VLM directly (scanned/image PDF)


class ParserDispatcher:
    """Route file parsing based on extension and content type."""

    def __init__(self, vlm_config=None):
        self._docling = DoclingParser()
        self._docx = DocxParser()
        self._excel = ExcelParser()
        self._text = TextParser()
        self._vlm_config = vlm_config

    def supports(self, file_path: str | Path) -> bool:
        """Check if we can parse this file type."""
        ext = Path(file_path).suffix.lower()
        return ext in (PDF_EXTS | DOC_EXTS | DOCX_EXTS | XLSX_EXTS | IMAGE_EXTS | TEXT_EXTS)

    async def parse(self, file_path: str | Path, doc_id: str, kb_id: str) -> ParsedDocument:
        """Parse a file using the appropriate parser. All sync parsers wrapped in to_thread."""
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext in PDF_EXTS:
            return await self._parse_pdf(path, doc_id, kb_id)
        elif ext in DOC_EXTS:
            return await self._parse_doc(path, doc_id, kb_id)
        elif ext in DOCX_EXTS:
            return await asyncio.to_thread(self._docx.parse, path, doc_id, kb_id)
        elif ext in XLSX_EXTS:
            return await asyncio.to_thread(self._excel.parse, path, doc_id, kb_id)
        elif ext in IMAGE_EXTS:
            return await self._parse_image(path, doc_id, kb_id)
        elif ext in TEXT_EXTS:
            return await asyncio.to_thread(self._text.parse, path, doc_id, kb_id)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    async def _parse_pdf(self, path: Path, doc_id: str, kb_id: str) -> ParsedDocument:
        """Parse PDF with three-tier fallback: Docling → PyMuPDF → VLM."""
        from app.services.parsing.pdf_probe import probe_pdf
        from app.config import settings

        # Phase 0: Quick probe (<1 second)
        probe = await asyncio.to_thread(probe_pdf, path)
        density = probe["chars_per_page"]
        page_count = probe["page_count"]
        logger.info("PDF probe: %d pages, %d total chars, %.0f chars/page",
                     page_count, probe["total_chars"], density)

        # Tier 3: Low text density → scanned PDF, go directly to VLM
        if density < TEXT_DENSITY_LOW:
            logger.info("PDF routing: VLM (scanned, text density=%.0f)", density)
            return await self._parse_via_vlm(path, doc_id, kb_id, page_count)

        # Fast path: very high text density → PyMuPDF (pure text, no layout analysis needed)
        if density >= TEXT_DENSITY_VERY_HIGH:
            logger.info("PDF routing: PyMuPDF direct (text density=%.0f, pure text PDF)", density)
            try:
                result = await asyncio.to_thread(self._parse_via_pymupdf, path, doc_id, kb_id)
                if result and result.content and len(result.content.strip()) > 100:
                    logger.info("PyMuPDF extracted %d chars", len(result.content))
                    return result
                logger.warning("PyMuPDF extracted too little text (%d chars), trying Docling",
                              len(result.content) if result and result.content else 0)
            except Exception as e:
                logger.warning("PyMuPDF failed: %s, trying Docling", e)

            # PyMuPDF failed on high-density PDF → try Docling
            try:
                timeout = settings.docling_timeout_seconds
                result = await asyncio.wait_for(
                    asyncio.to_thread(self._docling.parse, path, doc_id, kb_id, True),
                    timeout=timeout,
                )
                logger.info("Docling fallback succeeded")
                return result
            except Exception as e:
                logger.warning("Docling fallback failed: %s, trying VLM", e)
                return await self._parse_via_vlm(path, doc_id, kb_id, page_count)

        # Medium text density → Docling (best quality for tables/charts)
        logger.info("PDF routing: Docling (text density=%.0f)", density)
        try:
            fast_mode = density > TEXT_DENSITY_HIGH
            timeout = settings.docling_timeout_seconds
            result = await asyncio.wait_for(
                asyncio.to_thread(self._docling.parse, path, doc_id, kb_id, fast_mode),
                timeout=timeout,
            )
            logger.info("Docling parse succeeded (fast_mode=%s)", fast_mode)
            return result
        except asyncio.TimeoutError:
            logger.warning("Docling timed out (%ds), falling back to PyMuPDF", timeout)
        except Exception as e:
            logger.warning("Docling failed: %s, falling back to PyMuPDF", e)

        # Tier 2: PyMuPDF direct text extraction (fast, no models needed)
        logger.info("PDF routing: PyMuPDF fallback (text density=%.0f)", density)
        try:
            result = await asyncio.to_thread(self._parse_via_pymupdf, path, doc_id, kb_id)
            if result and result.content and len(result.content.strip()) > 100:
                logger.info("PyMuPDF extracted %d chars", len(result.content))
                return result
            logger.warning("PyMuPDF extracted too little text (%d chars), trying VLM",
                          len(result.content) if result and result.content else 0)
        except Exception as e:
            logger.warning("PyMuPDF failed: %s, trying VLM", e)

        # Tier 3: VLM multimodal (last resort)
        return await self._parse_via_vlm(path, doc_id, kb_id, page_count)

    def _parse_via_pymupdf(self, path: Path, doc_id: str, kb_id: str) -> ParsedDocument:
        """Extract text from PDF using PyMuPDF (fitz) directly. No models needed."""
        import fitz

        doc = fitz.open(str(path))
        try:
            pages_text = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                if text and text.strip() and len(text.strip()) > 20:
                    pages_text.append(f"## Page {page_num + 1}\n\n{text.strip()}")

            page_count = len(doc)
        finally:
            doc.close()

        content = "\n\n---\n\n".join(pages_text) if pages_text else ""

        return ParsedDocument(
            doc_id=doc_id,
            kb_id=kb_id,
            filename=path.name,
            file_type=DocType.PDF,
            file_hash=compute_file_hash(path),
            content=content,
            metadata={
                "parser": "pymupdf",
                "page_count": page_count,
                "text_length": len(content),
            },
        )

    async def _parse_via_vlm(self, path: Path, doc_id: str, kb_id: str, page_count: int) -> ParsedDocument:
        """Parse PDF using VLM multimodal OCR. Uses longer timeout."""
        from app.config import settings

        if not self._vlm_config:
            raise RuntimeError(
                f"PDF needs VLM parsing ({page_count} pages, low text density) "
                "but VLM is not configured. Please set up a VLM model config."
            )

        # VLM is slow — allow up to 30s per page
        vlm_timeout = max(settings.parse_timeout_seconds, page_count * 30)
        logger.info("VLM parse: %d pages, timeout=%ds", page_count, vlm_timeout)

        parser = VLMOCRParser(self._vlm_config)
        return await asyncio.wait_for(
            parser.parse(path, doc_id, kb_id),
            timeout=vlm_timeout,
        )

    async def _parse_image(self, path: Path, doc_id: str, kb_id: str) -> ParsedDocument:
        """Parse image using VLM OCR."""
        if self._vlm_config is None:
            raise ValueError("VLM not configured, cannot parse images")
        parser = ImageParser(self._vlm_config)
        return await parser.parse(path, doc_id, kb_id)

    async def _parse_doc(self, path: Path, doc_id: str, kb_id: str) -> ParsedDocument:
        """Parse legacy .doc with 6-tier fallback chain (see doc_converter.py)."""
        file_hash = compute_file_hash(path)

        # Use the centralized extract_text_from_doc which handles all tiers
        text = await extract_text_from_doc(path)

        if not text or not text.strip():
            raise RuntimeError(
                f"All .doc parsing methods failed for {path.name}. "
                "Install LibreOffice (libreoffice-writer), catdoc, or antiword for .doc support."
            )

        return ParsedDocument(
            doc_id=doc_id,
            kb_id=kb_id,
            filename=path.name,
            file_type=DocType.DOCX,
            file_hash=file_hash,
            content=text,
            metadata={
                "parser": "doc_multi_tier",
                "text_length": len(text),
            },
        )
