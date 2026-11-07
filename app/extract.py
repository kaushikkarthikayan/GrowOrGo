"""Part 1: turn uploaded files into plain text.
PDF -> pdfplumber, falls back to OCR for scanned pages.
DOCX -> python-docx (paragraphs + tables).
Images (PNG/JPG) -> OCR.
TXT -> read directly."""
import io
import re
import shutil

import pdfplumber
from docx import Document

from .config import TESSERACT_CMD

# A page with fewer characters than this is treated as "probably scanned".
MIN_CHARS_PER_PAGE = 40


def _tesseract_ready() -> bool:
    try:
        import pytesseract
    except ImportError:
        return False
    if TESSERACT_CMD and shutil.which(TESSERACT_CMD):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        return True
    return shutil.which("tesseract") is not None


def _ocr_image(image) -> str:
    import pytesseract

    return pytesseract.image_to_string(image)


def _from_pdf(data: bytes) -> tuple[str, list[str], str]:
    warnings: list[str] = []
    method = "text"
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")

    weak = [i for i, t in enumerate(pages) if len(t.strip()) < MIN_CHARS_PER_PAGE]
    if weak:
        if _tesseract_ready():
            import pymupdf as fitz
            from PIL import Image

            doc = fitz.open(stream=data, filetype="pdf")
            for i in weak:
                pix = doc[i].get_pixmap(dpi=200)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                pages[i] = _ocr_image(img)
            method = "text+ocr" if len(weak) < len(pages) else "ocr"
        else:
            warnings.append(
                f"{len(weak)} page(s) look scanned but Tesseract OCR is not installed, "
                "so their text could not be read."
            )
    return "\n".join(pages), warnings, method


def _from_docx(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _from_image(data: bytes) -> tuple[str, list[str]]:
    if not _tesseract_ready():
        return "", ["Images need Tesseract OCR, which is not installed."]
    from PIL import Image

    return _ocr_image(Image.open(io.BytesIO(data))), []


def extract_text(filename: str, data: bytes) -> dict:
    """Return {"text", "method", "warnings"} for one uploaded file."""
    name = (filename or "").lower()
    warnings: list[str] = []

    if name.endswith(".pdf"):
        text, warnings, method = _from_pdf(data)
    elif name.endswith(".docx"):
        text, method = _from_docx(data), "docx"
    elif name.endswith((".png", ".jpg", ".jpeg")):
        text, warnings = _from_image(data)
        method = "ocr"
    elif name.endswith(".txt"):
        text, method = data.decode("utf-8", errors="ignore"), "text"
    else:
        raise ValueError("Unsupported file type. Use PDF, DOCX, PNG, JPG or TXT.")

    # Some PDFs store bullet symbols as "(cid:127)" - turn them into real bullets.
    text = re.sub(r"\(cid:\d+\)", "•", text)
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not text:
        warnings.append("No text could be read from this file.")
    return {"text": text, "method": method, "warnings": warnings}
