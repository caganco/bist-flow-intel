"""Integration tests for TSG scraper persistence (no Playwright/OCR).

Exercises the DB layer directly: company dedup and role idempotency against a
live database. The Playwright/OCR path is CAPTCHA-gated and validated manually.
"""
import pytest
from sqlalchemy import delete

from trailing_edge.models.unlisted import PersonUnlistedRole, UnlistedCompany
from trailing_edge.scrapers.ticaret_sicil.parser import GazetteRecord, IlanRow, RawPerson
from trailing_edge.scrapers.ticaret_sicil.scraper import _upsert_company, _upsert_role

_TEST_SICIL = "ZZTEST-777111"


def _notice() -> IlanRow:
    return IlanRow(
        company_name="ZZ Test Şirketi A.Ş.",
        sicil_no=_TEST_SICIL,
        city="ANKARA",
        gazette_date=None,
        gazette_issue="9999",
        page_no="1",
        ilan_type="TEST",
        pdf_guid="zz-test-guid",
    )


@pytest.mark.asyncio
async def test_upsert_company_dedups_on_sicil_no(db_session):
    """Inserting the same sicil_no twice returns the same company id."""
    rec = GazetteRecord(company_name="ZZ Test Şirketi A.Ş.", raw_text="x", persons=[])
    try:
        id1 = await _upsert_company(db_session, rec, _notice(), "http://x")
        id2 = await _upsert_company(db_session, rec, _notice(), "http://x")
        assert id1 == id2
    finally:
        await db_session.execute(
            delete(UnlistedCompany).where(UnlistedCompany.sicil_no == _TEST_SICIL)
        )


@pytest.mark.asyncio
async def test_upsert_role_idempotent_and_unmatched(db_session):
    """An unmatched person → person_id NULL, inserted once; re-insert is a no-op."""
    rec = GazetteRecord(company_name="ZZ Test Şirketi A.Ş.", raw_text="x", persons=[])
    person = RawPerson(name="ZZ TEST KİŞİ", role="Yönetim Kurulu Üyesi")
    company_id = await _upsert_company(db_session, rec, _notice(), "http://x")
    try:
        inserted1, matched1 = await _upsert_role(db_session, company_id, person, [])
        assert inserted1 is True
        assert matched1 is False  # empty KAP list → no match

        inserted2, _ = await _upsert_role(db_session, company_id, person, [])
        assert inserted2 is False  # uq constraint → idempotent
    finally:
        await db_session.execute(
            delete(PersonUnlistedRole).where(
                PersonUnlistedRole.unlisted_company_id == company_id
            )
        )
        await db_session.execute(
            delete(UnlistedCompany).where(UnlistedCompany.id == company_id)
        )
