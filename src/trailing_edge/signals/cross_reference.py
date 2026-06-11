"""KAP listed ↔ TSG unlisted cross-reference engine.

Joins a KAP actor's listed-company footprint (board roles + insider clusters)
with their TSG unlisted-company network into a single ActorFootprint, and
builds a CrossReferenceReport across the high-value actor set.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select, text

from trailing_edge.core.db import get_session
from trailing_edge.core.logging import get_logger
from trailing_edge.models.graph import Person
from trailing_edge.scrapers.kap.helpers import normalize_name

_log = get_logger(__name__)


@dataclass
class ActorFootprint:
    person_id: int
    full_name: str
    listed_companies: list[dict]      # ticker, company_name, role, role_type
    listed_clusters: list[dict]       # ticker, cluster_score, window_start/end, insider_count
    unlisted_companies: list[dict]    # name, city, district, founded_date, role, match_confidence, match_method
    unknown_associates: list[dict]    # raw_person_name, company_name, role, match_confidence
    actor_score: float = 0.0


@dataclass
class CrossReferenceReport:
    as_of_date: date
    actors: list[ActorFootprint]
    total_listed: int
    total_unlisted: int
    total_unknown_associates: int


_Q1_LISTED_COMPANIES = text("""
    SELECT c.ticker, c.company_name, pcr.role, pcr.role_type
    FROM person_company_roles pcr
    JOIN companies c ON c.id = pcr.company_id
    WHERE pcr.person_id = :person_id AND pcr.valid_until IS NULL
    ORDER BY pcr.role_type
""")

# Cluster + BUY transactions for the actor. insider_name is selected so we can
# filter in Python by normalized name (SQL has no Turkish-aware normalizer).
_Q2_CLUSTERS = text("""
    SELECT DISTINCT ic.ticker, ic.cluster_score, ic.window_start, ic.window_end,
           ic.insider_count, kit.insider_name
    FROM insider_clusters ic
    JOIN kap_insider_transactions kit
      ON kit.ticker = ic.ticker
     AND kit.transaction_date BETWEEN ic.window_start AND ic.window_end
    WHERE kit.transaction_type = 'BUY'
    ORDER BY ic.cluster_score DESC
""")

_Q3_UNLISTED = text("""
    SELECT uc.name, uc.city, uc.district, uc.founded_date, uc.company_type,
           pur.role, pur.match_confidence, pur.match_method
    FROM person_unlisted_roles pur
    JOIN unlisted_companies uc ON uc.id = pur.unlisted_company_id
    WHERE pur.person_id = :person_id
    ORDER BY uc.founded_date DESC NULLS LAST
""")

_Q4_UNKNOWN_ASSOCIATES = text("""
    SELECT pur2.raw_person_name, uc.name AS company_name, pur2.role, pur2.match_confidence
    FROM person_unlisted_roles pur1
    JOIN unlisted_companies uc ON uc.id = pur1.unlisted_company_id
    JOIN person_unlisted_roles pur2
      ON pur2.unlisted_company_id = uc.id AND pur2.person_id IS NULL
    WHERE pur1.person_id = :person_id
    ORDER BY uc.name, pur2.raw_person_name
""")

_Q_SHARED_UNLISTED = text("""
    SELECT uc.name, uc.city, uc.founded_date
    FROM person_unlisted_roles pur_a
    JOIN person_unlisted_roles pur_b
      ON pur_a.unlisted_company_id = pur_b.unlisted_company_id
    JOIN unlisted_companies uc ON uc.id = pur_a.unlisted_company_id
    WHERE pur_a.person_id = :a AND pur_b.person_id = :b
    ORDER BY uc.founded_date DESC NULLS LAST
""")


def _f(value) -> float | None:
    """Decimal/None → float/None (for JSON + template safety)."""
    return float(value) if value is not None else None


async def get_actor_footprint(person_id: int, actor_score: float = 0.0) -> ActorFootprint:
    """Full financial footprint for one KAP actor (listed + unlisted)."""
    async with get_session() as session:
        person = (
            await session.execute(select(Person).where(Person.id == person_id))
        ).scalar_one_or_none()
        if person is None:
            return ActorFootprint(person_id, "", [], [], [], [], actor_score)
        person_norm = person.name_normalized

        listed_companies = [
            {
                "ticker": r.ticker,
                "company_name": r.company_name,
                "role": r.role,
                "role_type": r.role_type,
            }
            for r in (await session.execute(_Q1_LISTED_COMPANIES, {"person_id": person_id})).all()
        ]

        cluster_rows = (await session.execute(_Q2_CLUSTERS)).all()
        best_per_ticker: dict[str, dict] = {}
        for r in cluster_rows:
            if normalize_name(r.insider_name) != person_norm:
                continue
            score = _f(r.cluster_score) or 0.0
            if r.ticker not in best_per_ticker or score > best_per_ticker[r.ticker]["cluster_score"]:
                best_per_ticker[r.ticker] = {
                    "ticker": r.ticker,
                    "cluster_score": _f(r.cluster_score),
                    "window_start": r.window_start,
                    "window_end": r.window_end,
                    "insider_count": r.insider_count,
                }
        listed_clusters = list(best_per_ticker.values())

        unlisted_companies = [
            {
                "name": r.name,
                "city": r.city,
                "district": r.district,
                "founded_date": r.founded_date,
                "company_type": r.company_type,
                "role": r.role,
                "match_confidence": _f(r.match_confidence),
                "match_method": r.match_method,
            }
            for r in (await session.execute(_Q3_UNLISTED, {"person_id": person_id})).all()
        ]

        unknown_associates = [
            {
                "raw_person_name": r.raw_person_name,
                "company_name": r.company_name,
                "role": r.role,
                "match_confidence": _f(r.match_confidence),
            }
            for r in (await session.execute(_Q4_UNKNOWN_ASSOCIATES, {"person_id": person_id})).all()
        ]

    return ActorFootprint(
        person_id=person_id,
        full_name=person.full_name,
        listed_companies=listed_companies,
        listed_clusters=listed_clusters,
        unlisted_companies=unlisted_companies,
        unknown_associates=unknown_associates,
        actor_score=actor_score,
    )


async def get_actors_with_unlisted_links() -> list[tuple[int, str]]:
    """Persons with at least one matched unlisted company role."""
    async with get_session() as session:
        rows = (await session.execute(text("""
            SELECT DISTINCT p.id, p.full_name
            FROM person_unlisted_roles pur
            JOIN persons p ON p.id = pur.person_id
            WHERE pur.person_id IS NOT NULL
            ORDER BY p.full_name
        """))).all()
    return [(r.id, r.full_name) for r in rows]


async def build_cross_reference_report(
    person_ids: list[int] | None = None,
    top_n: int = 20,
) -> CrossReferenceReport:
    """Footprint report. person_ids=None → high-value actor set merged with unlisted-link actors."""
    if person_ids is None:
        from trailing_edge.scrapers.ticaret_sicil.targets import get_high_value_actors

        top_ids = [pid for pid, _ in await get_high_value_actors(top_n)]
        unlisted_ids = [pid for pid, _ in await get_actors_with_unlisted_links()]
        seen: set[int] = set()
        actor_ids: list[int] = []
        for pid in top_ids + unlisted_ids:
            if pid not in seen:
                seen.add(pid)
                actor_ids.append(pid)
    else:
        actor_ids = person_ids

    actors = [await get_actor_footprint(pid) for pid in actor_ids]

    total_listed = sum(len(a.listed_companies) for a in actors)

    # Count distinct unlisted companies from DB (avoids double-counting shared companies)
    async with get_session() as session:
        total_unlisted_db = (await session.execute(
            text("SELECT COUNT(DISTINCT unlisted_company_id) FROM person_unlisted_roles WHERE person_id IS NOT NULL")
        )).scalar() or 0

        # Orphan associates: unmatched persons in the same unlisted company network
        total_unknown = (
            await session.execute(
                text("SELECT COUNT(*) FROM person_unlisted_roles WHERE person_id IS NULL")
            )
        ).scalar() or 0

    _log.info(
        "cross_reference_built",
        actors=len(actors),
        listed=total_listed,
        unlisted=total_unlisted_db,
        unknown=total_unknown,
    )
    return CrossReferenceReport(
        as_of_date=date.today(),
        actors=actors,
        total_listed=total_listed,
        total_unlisted=int(total_unlisted_db),
        total_unknown_associates=int(total_unknown),
    )


async def find_shared_unlisted_companies(person_id_a: int, person_id_b: int) -> list[dict]:
    """Unlisted companies where both actors hold a matched role (TSG interlock)."""
    async with get_session() as session:
        rows = (
            await session.execute(_Q_SHARED_UNLISTED, {"a": person_id_a, "b": person_id_b})
        ).all()
    return [
        {"name": r.name, "city": r.city, "founded_date": r.founded_date}
        for r in rows
    ]
