"""Unit tests for TSG parsers - driven by real captured fixtures."""
from datetime import date
from pathlib import Path

import pytest

from flow_intel.scrapers.ticaret_sicil.parser import (
    parse_gazette_ocr,
    parse_search_results,
)

FIXTURES = Path(__file__).parents[4] / "tests" / "fixtures" / "tsg"


@pytest.fixture
def search_html() -> str:
    return (FIXTURES / "sample_search_results.html").read_text(encoding="utf-8")


@pytest.fixture
def gazette_ocr() -> str:
    return (FIXTURES / "sample_gazette_ocr.txt").read_text(encoding="utf-8")


# ── parse_search_results ──────────────────────────────────────────────────────

def test_parse_search_results_empty_page():
    """Empty HTML → [] (no crash)."""
    assert parse_search_results("<html><body></body></html>") == []


def test_parse_search_results_finds_rows(search_html):
    """Real search page → ilan rows with company, sicil, guid."""
    rows = parse_search_results(search_html)
    assert len(rows) >= 1
    first = rows[0]
    assert "HERA TEKN" in first.company_name.upper()
    assert first.sicil_no == "317958"
    assert first.pdf_guid  # non-empty


def test_parse_search_results_parses_date(search_html):
    """Turkish DD.MM.YYYY dates parse into date objects."""
    rows = parse_search_results(search_html)
    dated = [r for r in rows if r.gazette_date is not None]
    assert dated
    assert all(isinstance(r.gazette_date, date) for r in dated)


# ── parse_gazette_ocr - block isolation ─────────────────────────────────────

def test_gazette_ocr_isolates_target_block(gazette_ocr):
    """A gazette page holds many companies; the target's block is isolated and
    its people extracted - Rıza Kandemir appears in Hera Teknik."""
    record = parse_gazette_ocr(gazette_ocr, "Hera Teknik Yapi")
    assert record is not None
    assert "HERA TEKN" in record.company_name.upper()
    names = {p.name.upper() for p in record.persons}
    assert any("KANDEM" in n for n in names)
    assert record.raw_text  # forensic source preserved


def test_gazette_ocr_does_not_leak_other_company(gazette_ocr):
    """Target Hera Teknik must NOT contain another company's directors
    (Hayri Dirice belongs to Dirice Tekstil, a different block)."""
    record = parse_gazette_ocr(gazette_ocr, "Hera Teknik Yapi")
    assert record is not None
    names = {p.name.upper() for p in record.persons}
    assert not any("DIRICE" in n or "DİRİCE" in n for n in names)


def test_gazette_ocr_selects_correct_block_for_other_company(gazette_ocr):
    """Fuzzy block selection works for a different target on the same page."""
    record = parse_gazette_ocr(gazette_ocr, "Dirice Tekstil")
    assert record is not None
    assert "DIRİCE" in record.company_name.upper() or "DİRİCE" in record.company_name.upper()
    names = {p.name.upper() for p in record.persons}
    assert any("DİRİCE" in n or "DIRICE" in n for n in names)


def test_gazette_ocr_no_match_returns_none(gazette_ocr):
    """A company not on the page → None (refuse to attribute wrong directors)."""
    assert parse_gazette_ocr(gazette_ocr, "Tamamen Alakasız Holding A.Ş.") is None


def test_gazette_ocr_empty_returns_none():
    """Empty OCR text → None."""
    assert parse_gazette_ocr("", "Hera Teknik") is None


def test_gazette_ocr_person_names_clean(gazette_ocr):
    """Extracted names have no leading/trailing whitespace."""
    record = parse_gazette_ocr(gazette_ocr, "Hera Teknik Yapi")
    assert record is not None
    for p in record.persons:
        assert p.name == p.name.strip()
        assert p.name
