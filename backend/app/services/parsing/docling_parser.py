"""Docling-based document parser for PDF (text) and other supported formats.

Docling is optional — if not installed, parse() raises ImportError and the
dispatcher falls back to PyMuPDF or VLM.
"""

from pathlib import Path

from app.services.parsing.types import DocType, ParsedDocument

# Local model directory — pre-downloaded for offline/container use
_DOCLING_ARTIFACTS_PATH = Path(__file__).parent.parent.parent.parent / "docling_models"


def compute_file_hash(file_path: str | Path) -> str:
    """Compute SHA256 hash of a file."""
    import hashlib
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _get_artifacts_path() -> Path | None:
    """Resolve Docling artifacts path. Returns None if models not available."""
    if _DOCLING_ARTIFACTS_PATH.is_dir():
        return _DOCLING_ARTIFACTS_PATH
    return None


def _check_docling_available() -> None:
    """Raise ImportError with a helpful message if docling is not installed."""
    try:
        import docling  # noqa: F401
    except ImportError:
        raise ImportError(
            "Docling is not installed. Install with: pip install docling\n"
            "PDF parsing will use PyMuPDF fallback instead."
        )


class DoclingParser:
    """Parse documents using Docling (optional dependency)."""

    def __init__(self):
        self._converter = None
        self._converter_fast = None

    @property
    def converter(self):
        """Lazy-init full DocumentConverter with OCR support."""
        if self._converter is None:
            _check_docling_available()
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.datamodel.base_models import InputFormat

            artifacts = _get_artifacts_path()
            pipeline_opts = PdfPipelineOptions(artifacts_path=artifacts)
            self._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)
                },
            )
        return self._converter

    @property
    def converter_fast(self):
        """Lazy-init fast DocumentConverter (no OCR, no page images)."""
        if self._converter_fast is None:
            _check_docling_available()
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.datamodel.base_models import InputFormat

            artifacts = _get_artifacts_path()
            pipeline_opts = PdfPipelineOptions(
                generate_page_images=False,
                do_ocr=False,
                artifacts_path=artifacts,
            )
            self._converter_fast = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)
                },
            )
        return self._converter_fast

    def supports(self, file_path: str | Path) -> bool:
        """Check if Docling can parse this file."""
        path = Path(file_path)
        return path.suffix.lower() in (".pdf", ".docx", ".pptx", ".html")

    def parse(self, file_path: str | Path, doc_id: str, kb_id: str, fast_mode: bool = False) -> ParsedDocument:
        """Parse a document and return Structured Markdown."""
        _check_docling_available()
        path = Path(file_path)
        conv = self.converter_fast if fast_mode else self.converter
        result = conv.convert(str(path))

        # Convert to markdown
        md_content = result.document.export_to_markdown()

        # Count pages
        page_count = len(result.document.pages) if hasattr(result.document, 'pages') else 0

        return ParsedDocument(
            doc_id=doc_id,
            kb_id=kb_id,
            filename=path.name,
            file_type=DocType.PDF,
            file_hash=compute_file_hash(path),
            content=md_content,
            metadata={
                "page_count": page_count,
                "text_length": len(md_content),
                "source": "docling_fast" if fast_mode else "docling",
            },
        )
