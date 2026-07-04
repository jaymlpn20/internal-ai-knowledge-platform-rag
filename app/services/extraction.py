"""Content extraction for PDFs (text + OCR fallback), text, markdown and code files."""
from __future__ import annotations

import io
import os
from dataclasses import dataclass, field

from app.config import get_settings

settings = get_settings()

# Map file extensions -> logical source type.
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rb", ".rs",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".kt", ".swift", ".scala", ".sh", ".sql",
}
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
TEXT_EXTENSIONS = {".txt", ".text", ".log", ".rst"}
PDF_EXTENSIONS = {".pdf"}


@dataclass
class ExtractedSegment:
    """A logical unit of extracted text plus provenance metadata."""

    text: str
    metadata: dict = field(default_factory=dict)


def detect_source_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in MARKDOWN_EXTENSIONS:
        return "markdown"
    if ext in CODE_EXTENSIONS:
        return "code"
    if ext in TEXT_EXTENSIONS:
        return "text"
    # Unknown extensions are treated as plain text so nothing silently fails.
    return "text"


def _read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _ocr_page(page) -> str:
    """Rasterize a PDF page and run Tesseract OCR on it."""
    import pytesseract
    from PIL import Image

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    pix = page.get_pixmap(dpi=settings.ocr_dpi)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(image).strip()


def extract_pdf(path: str) -> list[ExtractedSegment]:
    """Extract per-page text. Falls back to OCR for scanned/image pages."""
    import fitz  # PyMuPDF

    segments: list[ExtractedSegment] = []
    with fitz.open(path) as doc:
        for index, page in enumerate(doc):
            page_number = index + 1
            text = (page.get_text() or "").strip()
            method = "text"
            if len(text) < settings.ocr_min_chars:
                # Likely a scanned page with no embedded text layer.
                ocr_text = _ocr_page(page)
                if len(ocr_text) >= len(text):
                    text = ocr_text
                    method = "ocr"
            if text:
                segments.append(
                    ExtractedSegment(text=text, metadata={"page": page_number, "extraction": method})
                )
    return segments


def extract(path: str, source_type: str) -> list[ExtractedSegment]:
    """Return extracted segments for a stored file given its source type."""
    if source_type == "pdf":
        return extract_pdf(path)

    content = _read_text_file(path)
    if not content.strip():
        return []

    metadata: dict = {}
    if source_type == "code":
        metadata["language"] = _language_from_path(path)
    return [ExtractedSegment(text=content, metadata=metadata)]


def _language_from_path(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "typescript",
        ".jsx": "javascript", ".java": "java", ".go": "go", ".rb": "ruby", ".rs": "rust",
        ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp", ".php": "php",
        ".kt": "kotlin", ".swift": "swift", ".scala": "scala", ".sh": "bash", ".sql": "sql",
    }.get(ext, "unknown")
