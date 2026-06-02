"""OCR for Ticaret Sicil Gazetesi PDFs.

TSG gazette PDFs are scanned images (no text layer), so pdfminer/PyMuPDF
text extraction returns nothing. We render each page to a high-DPI bitmap
and run Tesseract with the Turkish language model.

System requirement: Tesseract OCR binary + tur.traineddata. See README.
"""
from __future__ import annotations

import io
import logging

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from flow_intel.core.config import get_config
from flow_intel.core.logging import get_logger

# Silence verbose debug output from PIL/pytesseract on each OCR call.
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("pytesseract").setLevel(logging.WARNING)

_log = get_logger(__name__)

_configured = False


def _configure_tesseract() -> tuple[str, int]:
    """Set pytesseract binary path from config; return (lang, dpi)."""
    global _configured
    cfg = get_config().get("tsg", {})
    cmd = cfg.get("tesseract_cmd", "").strip()
    if cmd and not _configured:
        pytesseract.pytesseract.tesseract_cmd = cmd
        _configured = True
    lang = cfg.get("ocr_lang", "tur")
    dpi = int(cfg.get("ocr_dpi", 300))
    return lang, dpi


def pdf_to_text(pdf_bytes: bytes) -> str:
    """Render every page of a scanned PDF and OCR it into a single string.

    Returns the concatenated OCR text across all pages, page-separated by
    form feeds. Empty string if the PDF has no pages.
    """
    lang, dpi = _configure_tesseract()

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_text: list[str] = []
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            pages_text.append(pytesseract.image_to_string(img, lang=lang))
    finally:
        doc.close()

    _log.info("ocr_done", pages=len(pages_text), chars=sum(len(p) for p in pages_text))
    return "\f".join(pages_text)
