"""OCR smoke test - skipped when Tesseract isn't installed (CI portability)."""
import shutil
from pathlib import Path

import pytest

from trailing_edge.core.config import get_config
from trailing_edge.scrapers.ticaret_sicil.ocr import pdf_to_text

FIXTURES = Path(__file__).parents[4] / "tests" / "fixtures" / "tsg"


def _tesseract_available() -> bool:
    cmd = get_config().get("tsg", {}).get("tesseract_cmd", "").strip()
    if cmd and Path(cmd).exists():
        return True
    return shutil.which("tesseract") is not None


@pytest.mark.skipif(not _tesseract_available(), reason="Tesseract not installed")
def test_pdf_to_text_extracts_turkish_names():
    """Scanned gazette PDF → OCR text containing the expected company + person."""
    pdf_bytes = (FIXTURES / "sample_gazette.pdf").read_bytes()
    text = pdf_to_text(pdf_bytes)
    assert "HERA TEKN" in text.upper()
    assert "KANDEM" in text.upper()  # Rıza Kandemir
