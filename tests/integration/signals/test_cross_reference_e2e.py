"""Integration tests for the cross-reference engine - requires a live test DB."""
from datetime import date

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _person_id(db_session, full_name: str) -> int | None:
    from trailing_edge.scrapers.kap.helpers import normalize_name

    norm = normalize_name(full_name)
    return (
        await db_session.execute(
            text("SELECT id FROM persons WHERE name_normalized = :n"), {"n": norm}
        )
    ).scalar_one_or_none()


async def test_get_actor_footprint_kandemir(db_session):
    """Rıza Kandemir footprint: ≥2 unlisted companies including Hera."""
    from trailing_edge.signals.cross_reference import get_actor_footprint

    pid = await _person_id(db_session, "RIZA KANDEMİR")
    if pid is None:
        pytest.skip("Kandemir not in DB")

    fp = await get_actor_footprint(pid)
    assert len(fp.unlisted_companies) >= 2
    assert any("HERA" in uc["name"].upper() for uc in fp.unlisted_companies)


async def test_build_cross_reference_report_no_crash(db_session):
    """Report builds and returns a CrossReferenceReport even on sparse data."""
    from trailing_edge.signals.cross_reference import (
        CrossReferenceReport,
        build_cross_reference_report,
    )

    report = await build_cross_reference_report(top_n=5)
    assert isinstance(report, CrossReferenceReport)
    assert report.as_of_date == date.today()


async def test_find_shared_unlisted_companies_kandemir_zorlu(db_session):
    """Kandemir + Zorlu share unlisted companies (Hera / Ral Enerji)."""
    from trailing_edge.signals.cross_reference import find_shared_unlisted_companies

    a = await _person_id(db_session, "RIZA KANDEMİR")
    b = await _person_id(db_session, "AHMET ZORLU")
    if a is None or b is None:
        pytest.skip("Kandemir or Zorlu not in DB")

    shared = await find_shared_unlisted_companies(a, b)
    assert isinstance(shared, list)
    assert len(shared) >= 1


async def test_forensic_report_includes_tsg_layer(db_session, tmp_path, monkeypatch):
    """KAPLM forensic HTML includes the TSG layer section."""
    monkeypatch.chdir(tmp_path)
    from trailing_edge.reports.forensic_report import generate_forensic_report

    path = await generate_forensic_report("KAPLM", output_format="html")
    content = path.read_text(encoding="utf-8")
    assert "Fiziki Dünya Bağlantıları" in content


async def test_get_actors_with_unlisted_links_includes_zorlu(db_session):
    """get_actors_with_unlisted_links returns Ahmet Zorlu (D4b coverage)."""
    from trailing_edge.signals.cross_reference import get_actors_with_unlisted_links

    actors = await get_actors_with_unlisted_links()
    names = [name for _, name in actors]
    assert any("ZORLU" in n.upper() for n in names), (
        "Ahmet Zorlu must appear - TSG data was seeded in TASK-008"
    )


async def test_build_cross_reference_report_includes_zorlu(db_session):
    """Cross-reference report contains both Kandemir (top-N) and Zorlu (unlisted-link)."""
    from trailing_edge.signals.cross_reference import build_cross_reference_report

    report = await build_cross_reference_report(top_n=10)
    names = [a.full_name.upper() for a in report.actors]
    # Use prefix "KANDEM" to avoid U+0130 İ vs ASCII I mismatch in full_name
    assert any("KANDEM" in n for n in names), "Kandemir must be in top-N actors"
    assert any("ZORLU" in n for n in names), "Zorlu must appear via unlisted-link merge"


async def test_kaplm_cluster_score_matches_db(db_session):
    """Kandemir footprint KAPLM cluster score equals the max score in DB."""
    from sqlalchemy import text

    from trailing_edge.signals.cross_reference import get_actor_footprint

    pid = await _person_id(db_session, "RIZA KANDEMİR")
    if pid is None:
        pytest.skip("Kandemir not in DB")

    max_score = (await db_session.execute(
        text("""
            SELECT MAX(ic.cluster_score)
            FROM insider_clusters ic
            JOIN kap_insider_transactions kit
              ON kit.ticker = ic.ticker
             AND kit.transaction_date BETWEEN ic.window_start AND ic.window_end
            WHERE ic.ticker = 'KAPLM'
              AND kit.transaction_type = 'BUY'
              AND kit.is_legal_entity = FALSE
        """)
    )).scalar()

    fp = await get_actor_footprint(pid)
    kaplm_clusters = [c for c in fp.listed_clusters if c["ticker"] == "KAPLM"]
    if not kaplm_clusters:
        pytest.skip("Kandemir has no KAPLM cluster entry")

    assert kaplm_clusters[0]["cluster_score"] == float(max_score), (
        "Footprint KAPLM score must equal DB max"
    )
