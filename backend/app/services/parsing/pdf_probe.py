"""Quick PDF text density probe for smart routing decisions."""

from pathlib import Path


def probe_pdf(file_path: str | Path) -> dict:
    """Extract text statistics from a PDF in <1 second.

    Uses PyMuPDF (fitz) which is already installed and used by vlm_ocr.

    Returns:
        dict with keys: page_count, total_chars, chars_per_page, has_text
    """
    import fitz

    doc = fitz.open(str(file_path))
    page_count = len(doc)
    total_chars = 0

    for page in doc:
        text = page.get_text() or ""
        total_chars += len(text.strip())

    doc.close()

    chars_per_page = total_chars / page_count if page_count > 0 else 0

    return {
        "page_count": page_count,
        "total_chars": total_chars,
        "chars_per_page": chars_per_page,
        "has_text": chars_per_page > 50,
    }
