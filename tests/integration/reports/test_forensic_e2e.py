"""Integration tests for forensic report — requires live DB + playwright."""
import pytest

pytestmark = pytest.mark.asyncio


async def test_generate_html_report_kaplm(db_session, tmp_path, monkeypatch):
    """KAPLM için HTML rapor üretiliyor, dosya oluşuyor, içeriği doğru."""
    monkeypatch.chdir(tmp_path)
    from flow_intel.reports.forensic_report import generate_forensic_report

    path = await generate_forensic_report("KAPLM", output_format="html")
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "KAPLM" in content
    assert "CONFIDENTIAL" in content


async def test_generate_pdf_report_kaplm(db_session, tmp_path, monkeypatch):
    """KAPLM için PDF rapor üretiliyor, >10KB."""
    monkeypatch.chdir(tmp_path)
    from flow_intel.reports.forensic_report import generate_forensic_report

    path = await generate_forensic_report("KAPLM", output_format="pdf")
    assert path.exists()
    assert path.stat().st_size > 10_000
