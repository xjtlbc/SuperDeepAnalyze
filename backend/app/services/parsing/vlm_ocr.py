"""VLM-based OCR parser for scanned PDFs and images."""

from pathlib import Path

from PIL import Image

from app.models.config import ModelConfig
from app.services.parsing.types import DocType, ParsedDocument
from app.services.parsing.docling_parser import compute_file_hash


# PDF text density threshold: if below this, treat as scanned
TEXT_DENSITY_THRESHOLD = 50  # characters per page


def detect_scanned_pdf(file_path: str | Path) -> bool:
    """Check if a PDF is likely a scanned document based on text density."""
    try:
        import pypdf
        reader = pypdf.PdfReader(str(file_path))
        total_text = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            total_text += len(text.strip())
        return total_text < TEXT_DENSITY_THRESHOLD * len(reader.pages)
    except ImportError:
        return True  # pypdf not installed, assume scanned
    except Exception:
        return True  # Assume scanned if can't extract text


def pdf_to_images(file_path: str | Path, dpi: int = 200) -> list[Image.Image]:
    """Convert PDF pages to PIL Images. Tries PyMuPDF first, falls back to pdf2image."""
    # Try PyMuPDF (fitz) — no external binary needed
    try:
        import fitz
        doc = fitz.open(str(file_path))
        images = []
        scale = dpi / 72.0
        for page in doc:
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
        doc.close()
        return images
    except ImportError:
        pass

    # Fallback to pdf2image
    try:
        from pdf2image import convert_from_path
        return convert_from_path(str(file_path), dpi=dpi)
    except ImportError:
        raise RuntimeError(
            "PDF-to-image conversion requires either PyMuPDF (fitz) "
            "or pdf2image with poppler installed."
        )


class VLMOCRParser:
    """Parse documents using VLM (Vision Language Model) for OCR."""

    def __init__(self, model_config: ModelConfig):
        self._config = model_config

    async def parse(self, file_path: str | Path, doc_id: str, kb_id: str) -> ParsedDocument:
        """Parse a document using VLM OCR."""
        path = Path(file_path)
        images = pdf_to_images(path)

        pages_text = []
        for i, img in enumerate(images):
            text = await self._ocr_image(img, page_num=i + 1)
            pages_text.append(f"## Page {i + 1}\n\n{text}")

        content = "\n\n---\n\n".join(pages_text)

        return ParsedDocument(
            doc_id=doc_id,
            kb_id=kb_id,
            filename=path.name,
            file_type=DocType.PDF,
            file_hash=compute_file_hash(path),
            content=content,
            metadata={
                "page_count": len(images),
                "source": "vlm_ocr",
            },
        )

    async def parse_image(self, file_path: str | Path, doc_id: str, kb_id: str) -> ParsedDocument:
        """Parse a single image file."""
        path = Path(file_path)
        img = Image.open(path)

        text = await self._ocr_image(img)

        return ParsedDocument(
            doc_id=doc_id,
            kb_id=kb_id,
            filename=path.name,
            file_type=DocType.IMAGE,
            file_hash=compute_file_hash(path),
            content=text,
            metadata={"source": "vlm_ocr"},
        )

    async def _ocr_image(self, image: Image.Image, page_num: int = 0) -> str:
        """Send image to VLM for OCR extraction."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            base_url=self._config.base_url,
            api_key=self._config.api_key,
        )

        # Save image temporarily as base64
        import base64
        import io

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请识别这张图片中的所有文字内容，包括印刷体和手写体。按从上到下的顺序输出，保持原有的段落结构。如果图片中有表格，请用 Markdown 表格格式输出。",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }
        ]

        response = await client.chat.completions.create(
            model=self._config.model_name,
            messages=messages,
            max_tokens=4096,
        )

        return response.choices[0].message.content or ""
