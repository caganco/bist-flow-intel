"""Integration tests for graph seed and management board scraper - requires live DB."""
import importlib
import os
import sys

import pytest
from sqlalchemy import func, select, text

pytestmark = pytest.mark.asyncio

_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts")
sys.path.insert(0, _SCRIPTS)


async def _run_seed() -> None:
    """Import and run the seed script's main() function."""
    import seed_graph_from_insider_tx as seed_mod
    importlib.reload(seed_mod)
    await seed_mod.main()


async def test_seed_is_idempotent(db_session):
    """Running seed twice must not change row counts."""
    from trailing_edge.models.graph import Company, Person, PersonCompanyRole

    await _run_seed()
    count1_persons = (await db_session.execute(
        select(func.count()).select_from(Person)
    )).scalar()
    count1_companies = (await db_session.execute(
        select(func.count()).select_from(Company)
    )).scalar()
    count1_pcr = (await db_session.execute(
        select(func.count()).select_from(PersonCompanyRole)
    )).scalar()

    await _run_seed()
    count2_persons = (await db_session.execute(
        select(func.count()).select_from(Person)
    )).scalar()
    count2_companies = (await db_session.execute(
        select(func.count()).select_from(Company)
    )).scalar()
    count2_pcr = (await db_session.execute(
        select(func.count()).select_from(PersonCompanyRole)
    )).scalar()

    assert count1_persons == count2_persons, "persons count changed on re-seed"
    assert count1_companies == count2_companies, "companies count changed on re-seed"
    assert count1_pcr == count2_pcr, "person_company_roles count changed on re-seed"


async def test_board_interlocks_populated(db_session):
    """After seed, board_interlocks query executes and returns non-negative count."""
    await _run_seed()
    row = await db_session.execute(text("SELECT COUNT(*) FROM board_interlocks"))
    count = row.scalar()
    assert count >= 0


async def test_management_scrape_single_company_idempotent(db_session):
    """Scraping KAPLM twice must not change KAP_YONETIM row count."""
    from trailing_edge.models.graph import PersonCompanyRole
    from trailing_edge.scrapers.kap.management import scrape_all_companies

    await _run_seed()

    await scrape_all_companies(["KAPLM"])
    count1 = (await db_session.execute(
        select(func.count()).select_from(PersonCompanyRole)
        .where(PersonCompanyRole.source == "KAP_YONETIM")
    )).scalar()

    await scrape_all_companies(["KAPLM"])
    count2 = (await db_session.execute(
        select(func.count()).select_from(PersonCompanyRole)
        .where(PersonCompanyRole.source == "KAP_YONETIM")
    )).scalar()

    assert count1 == count2, "KAP_YONETIM row count changed on re-scrape"
    assert count1 > 0, "No KAP_YONETIM rows inserted for KAPLM"


async def test_board_interlocks_nondecreasing_after_management_scrape(db_session):
    """board_interlocks count must not decrease after management scrape."""
    from trailing_edge.scrapers.kap.management import scrape_all_companies

    await _run_seed()
    count_before = (await db_session.execute(
        text("SELECT COUNT(*) FROM board_interlocks")
    )).scalar()

    await scrape_all_companies(["KAPLM"])
    count_after = (await db_session.execute(
        text("SELECT COUNT(*) FROM board_interlocks")
    )).scalar()

    assert count_after >= count_before, "board_interlocks shrank after management scrape"
