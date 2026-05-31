"""Integration tests: end-to-end scraper idempotency via respx mocking."""
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from flow_intel.models.base import Base
from flow_intel.models.kap import KapDisclosure, KapInsiderTransaction, ScraperRun
from flow_intel.scrapers.kap.insider import KapInsiderScraper
from flow_intel.storage.repository import KapRepository

FIXTURES_DIR = Path(__file__).parents[3] / "fixtures" / "kap"

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://flowuser:flowpass@localhost:5432/flow_intel_test",
)

# Minimal disclosure list response for the NASMED fixture
_NASMED_DISC_INDEX = "1611139"
_NASMED_DISC_ID = "test-uuid-nasmed-0001"

_DISCLOSURE_LIST = [
    {
        "disclosureIndex": _NASMED_DISC_INDEX,
        "disclosureId": _NASMED_DISC_ID,
        "disclosureClass": "DKB",
        "subject": "Pay Alım Satım Bildirimi",
        "isCorrection": False,
    }
]

_DISCLOSURE_DETAIL = {
    "disclosure": {
        "disclosureBasic": {
            "disclosureIndex": _NASMED_DISC_INDEX,
            "disclosureId": _NASMED_DISC_ID,
            "disclosureClass": "DUY",
            "summary": "Pay Alım Satım Bildirimi",
            "disclosureType": "ODA",
            "companyTitle": "NASMED ÖZEL SAĞLIK HİZMETLERİ TİCARET A.Ş.",
            "publishDate": "2026.05.26 09:10:35",
            "isChanged": None,
            "relatedStocks": "EGEPO",
        }
    },
    "disclosureBody": "",
    "attachments": [{"objId": "4028328c9e276fa9019e62e3ea3b3a10", "fileName": "EGEPO_55470.pdf"}],
}

_DISCLOSURE_LIST_ITEM = {
    "disclosureIndex": _NASMED_DISC_INDEX,
    "disclosureClass": "DKB",
    "subject": "Pay Alım Satım Bildirimi",
    "isChanged": None,
    "relatedStocks": "EGEPO",
    "kapTitle": "NASMED ÖZEL SAĞLIK HİZMETLERİ TİCARET A.Ş.",
    "publishDate": "26.05.2026 09:10:35",
}


@pytest.fixture(scope="module")
def event_loop_policy():
    """Use default asyncio policy."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        # Create the updated_at trigger manually
        await conn.execute(text("""
            CREATE OR REPLACE FUNCTION set_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
            $$ LANGUAGE plpgsql
        """))
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(test_engine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


def _make_mock_kap_client(pdf_bytes: bytes):
    """Return a mock KapClient that serves the NASMED fixture data."""
    mock = AsyncMock()
    mock.warmup = AsyncMock()
    mock.fetch_disclosure_list = AsyncMock(return_value=_DISCLOSURE_LIST)
    mock.fetch_disclosure_detail = AsyncMock(return_value=_DISCLOSURE_DETAIL)
    mock.fetch_pdf = AsyncMock(return_value=pdf_bytes)
    return mock


async def _run_with_mock(db_session_factory, pdf_bytes: bytes) -> ScraperRun:
    """Run the scraper with mocked KAP responses and injected session factory."""
    mock_client = _make_mock_kap_client(pdf_bytes)

    # Patch the session factory and the KapClient
    from flow_intel.scrapers.kap import insider as insider_mod

    orig_get_session = insider_mod.get_session

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def patched_session():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    with (
        patch.object(insider_mod, "get_session", patched_session),
        patch("flow_intel.scrapers.kap.insider.RateLimitedClient") as mock_rl,
        patch("flow_intel.scrapers.kap.insider.KapClient", return_value=mock_client),
    ):
        # Make RateLimitedClient a context manager that returns itself
        mock_rl_instance = AsyncMock()
        mock_rl.return_value.__aenter__ = AsyncMock(return_value=mock_rl_instance)
        mock_rl.return_value.__aexit__ = AsyncMock(return_value=False)

        scraper = KapInsiderScraper()
        await scraper.run(date(2026, 5, 25), date(2026, 5, 26))

    # Fetch the latest scraper run
    async with db_session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(ScraperRun).order_by(ScraperRun.id.desc()).limit(1)
        )
        return result.scalar_one()


@pytest.mark.asyncio
async def test_idempotent_double_ingest(test_engine, db_session_factory):
    pdf_bytes = (FIXTURES_DIR / "dkb_decoded_attachment_nasmed.pdf").read_bytes()

    run1 = await _run_with_mock(db_session_factory, pdf_bytes)
    assert run1.status == "SUCCESS"
    assert run1.records_inserted > 0

    async with db_session_factory() as session:
        from sqlalchemy import func, select

        count_after_first = (
            await session.execute(select(func.count()).select_from(KapInsiderTransaction))
        ).scalar()

    run2 = await _run_with_mock(db_session_factory, pdf_bytes)
    assert run2.status == "SUCCESS"
    assert run2.records_skipped == 1  # the disclosure itself was skipped (already exists)

    async with db_session_factory() as session:
        from sqlalchemy import func, select

        count_after_second = (
            await session.execute(select(func.count()).select_from(KapInsiderTransaction))
        ).scalar()

    assert count_after_first == count_after_second, (
        "DB row count must not change on second ingest"
    )


@pytest.mark.asyncio
async def test_disclosure_stored_with_correct_metadata(test_engine, db_session_factory):
    pdf_bytes = (FIXTURES_DIR / "dkb_decoded_attachment_nasmed.pdf").read_bytes()

    await _run_with_mock(db_session_factory, pdf_bytes)

    async with db_session_factory() as session:
        from sqlalchemy import select

        disc = (
            await session.execute(
                select(KapDisclosure).where(
                    KapDisclosure.kap_disclosure_id == _NASMED_DISC_INDEX
                )
            )
        ).scalar_one()

    assert disc.ticker == "EGEPO"
    assert disc.disclosure_class == "DKB"
    assert disc.is_correction is False
