"""Shared pytest fixtures."""
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "kap"


@pytest.fixture
def dkb_pdf_bytes() -> bytes:
    return (FIXTURES_DIR / "dkb_decoded_attachment_nasmed.pdf").read_bytes()


@pytest.fixture
def oda_html() -> str:
    return (FIXTURES_DIR / "sample_insider_disclosure.html").read_text(encoding="utf-8")


@pytest.fixture
def dkb_html() -> str:
    return (FIXTURES_DIR / "sample_insider_disclosure_dkb.html").read_text(encoding="utf-8")
