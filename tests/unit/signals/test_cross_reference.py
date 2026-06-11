"""Unit tests for the cross-reference dataclasses - no DB."""
from datetime import date

import pytest

from trailing_edge.signals.cross_reference import ActorFootprint, CrossReferenceReport


def test_actor_footprint_dataclass_fields():
    """ActorFootprint exposes all required fields in the expected order."""
    fp = ActorFootprint(
        person_id=1,
        full_name="RIZA KANDEMİR",
        listed_companies=[],
        listed_clusters=[],
        unlisted_companies=[
            {"name": "Hera Teknik", "city": "ANKARA",
             "match_confidence": 0.963, "match_method": "HIGH"}
        ],
        unknown_associates=[],
        actor_score=0.75,
    )
    assert fp.full_name == "RIZA KANDEMİR"
    assert len(fp.unlisted_companies) == 1
    assert fp.actor_score == 0.75


def test_cross_reference_report_totals():
    """Positional construction matches field order; totals stored as given."""
    report = CrossReferenceReport(
        as_of_date=date.today(),
        actors=[
            ActorFootprint(1, "A", [], [], [{"name": "X"}], [], 0.5),
            ActorFootprint(2, "B", [], [], [{"name": "Y"}, {"name": "Z"}], [], 0.3),
        ],
        total_listed=0,
        total_unlisted=3,
        total_unknown_associates=0,
    )
    assert report.total_unlisted == 3
    assert len(report.actors) == 2


@pytest.mark.asyncio
async def test_actor_footprint_deduplicates_clusters_by_ticker(monkeypatch):
    """Two cluster rows for the same ticker → only best score kept (D3 fix)."""
    from contextlib import asynccontextmanager
    from datetime import date as dt
    from unittest.mock import AsyncMock, MagicMock

    import trailing_edge.signals.cross_reference as mod
    from trailing_edge.scrapers.kap.helpers import normalize_name

    person_obj = MagicMock()
    person_obj.name_normalized = normalize_name("RIZA KANDEMIR")
    person_obj.full_name = "RIZA KANDEMIR"

    def _row(ticker, score, name, ws, we, count):
        r = MagicMock()
        r.ticker = ticker
        r.cluster_score = score
        r.insider_name = name
        r.window_start = ws
        r.window_end = we
        r.insider_count = count
        return r

    low = _row("KAPLM", 50.0, "RIZA KANDEMIR", dt(2025, 10, 1), dt(2025, 10, 5), 3)
    high = _row("KAPLM", 85.0, "RIZA KANDEMIR", dt(2025, 10, 31), dt(2025, 10, 31), 5)

    def _res_scalar(val):
        r = MagicMock()
        r.scalar_one_or_none.return_value = val
        return r

    def _res_all(rows):
        r = MagicMock()
        r.all.return_value = rows
        return r

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(side_effect=[
        _res_scalar(person_obj),
        _res_all([]),
        _res_all([low, high]),
        _res_all([]),
        _res_all([]),
    ])

    @asynccontextmanager
    async def mock_get_session():
        yield mock_session

    monkeypatch.setattr(mod, "get_session", mock_get_session)

    fp = await mod.get_actor_footprint(1, 0.5)
    assert len(fp.listed_clusters) == 1, "Two rows same ticker must deduplicate to one"
    assert fp.listed_clusters[0]["cluster_score"] == 85.0, "Dedup must keep max score"
