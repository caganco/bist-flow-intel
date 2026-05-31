"""High-value actor selection and seed management for TSG scraping.

Scores KAP persons by cluster activity (60%) + board interlock depth (40%)
and maps them to known unlisted companies via config/actor_seeds.yaml.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select, text

from flow_intel.core.db import get_session
from flow_intel.core.logging import get_logger
from flow_intel.models.graph import Person
from flow_intel.models.unlisted import PersonUnlistedRole, UnlistedCompany

_log = get_logger(__name__)

_SEEDS_FILE = Path(__file__).parents[4] / "config" / "actor_seeds.yaml"

# SQL: peak cluster_score per insider (BUY only, joined with clusters)
_CLUSTER_SCORE_SQL = text("""
    SELECT kit.insider_name,
           MAX(ic.cluster_score) AS peak_score
    FROM kap_insider_transactions kit
    JOIN insider_clusters ic
      ON ic.ticker = kit.ticker
     AND kit.transaction_date BETWEEN ic.window_start AND ic.window_end
    WHERE kit.transaction_type = 'BUY'
      AND kit.is_legal_entity = FALSE
    GROUP BY kit.insider_name
""")

# SQL: board interlock depth per person
_INTERLOCK_SQL = text("""
    SELECT person_name,
           COUNT(*) AS interlock_count
    FROM board_interlocks
    GROUP BY person_name
""")


_LEGAL_ENTITY_MARKERS = [
    # Variants ending with İ (U+0130): casefold gives "i̇" which breaks substring
    # matching mid-word (e.g. "HOLDİNG" → "holdi̇ng", "anonim" not in "anoni̇m").
    # Shorter prefixes that end before the combining dot are safe.
    "anonim", "anoni",
    " a.ş", "a.s.", "holding", "holdi",
    "ortaklığı", "limited", " ltd",
    "şti", "sermayesi", "telekom", "teknoloji", "san.ve tic", "sanayi ve ticaret",
    "yatırım ortaklığı",
]


def is_legal_entity_name(name: str) -> bool:
    """Return True if name looks like a company rather than a natural person."""
    n = name.casefold()
    return any(m in n for m in _LEGAL_ENTITY_MARKERS)


def load_actor_seeds() -> dict[str, list[str]]:
    """Load config/actor_seeds.yaml → {full_name: [company_search_strings]}."""
    if not _SEEDS_FILE.exists():
        return {}
    with open(_SEEDS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    actors = data.get("actors", {})
    # Normalise: None / empty list → []
    return {name: (companies or []) for name, companies in actors.items()}


def validate_actor_seeds() -> dict[str, list[str]]:
    """Validate actor_seeds.yaml: drop empty-seed actors and sub-5-char names.

    - Empty list → skip (log: actor_skipped, reason=no_seeds)
    - Company name < 5 chars → warn + skip (TSG minimum search requirement)
    - Returns {actor_name: [valid_company_names]}.
    """
    seeds = load_actor_seeds()
    valid: dict[str, list[str]] = {}
    for actor, companies in seeds.items():
        if not companies:
            _log.info("actor_skipped", actor=actor, reason="no_seeds")
            continue
        valid_companies = [c for c in companies if len(c) >= 5]
        if len(valid_companies) < len(companies):
            _log.warning("short_company_names_skipped", actor=actor)
        if valid_companies:
            valid[actor] = valid_companies
    return valid


async def get_high_value_actors(top_n: int = 20) -> list[tuple[int, str]]:
    """Rank KAP persons by composite score and return top_n as [(person_id, full_name)].

    Scoring:
      cluster_score_norm  = peak_cluster_score / global_max  (0–1)
      interlock_norm      = interlock_count     / global_max  (0–1)
      composite           = cluster_score_norm * 0.6 + interlock_norm * 0.4

    Both signals are normalised to [0, 1] by dividing by the respective
    maximum value across all actors (simple, no outlier distortion at this scale).
    """
    async with get_session() as session:
        cluster_rows = (await session.execute(_CLUSTER_SCORE_SQL)).all()
        interlock_rows = (await session.execute(_INTERLOCK_SQL)).all()

        # persons table for id lookup
        persons = {
            r.name_normalized: (r.id, r.full_name)
            for r in (await session.execute(select(Person))).scalars().all()
        }

    # Build score maps keyed by normalized name
    from flow_intel.scrapers.kap.helpers import normalize_name

    cluster_map: dict[str, float] = {
        normalize_name(r.insider_name): float(r.peak_score)
        for r in cluster_rows
    }
    interlock_map: dict[str, int] = {
        normalize_name(r.person_name): int(r.interlock_count)
        for r in interlock_rows
    }

    max_cluster   = max(cluster_map.values(),   default=1.0)
    max_interlock = max(interlock_map.values(), default=1)

    scores: list[tuple[float, int, str]] = []
    for norm_name, (pid, full_name) in persons.items():
        c_norm = cluster_map.get(norm_name, 0.0)   / max_cluster
        i_norm = interlock_map.get(norm_name, 0)   / max_interlock
        composite = c_norm * 0.6 + i_norm * 0.4
        if composite > 0 and not is_legal_entity_name(full_name):
            scores.append((composite, pid, full_name))

    scores.sort(reverse=True)
    result = [(pid, name) for _, pid, name in scores[:top_n]]
    _log.info("high_value_actors_selected", count=len(result))
    return result


async def get_seed_companies_for_actor(
    person_name: str,
    actor_seeds: dict[str, list[str]],
) -> list[str]:
    """Return company search strings for a given KAP actor.

    1. Exact name lookup in actor_seeds.yaml.
    2. Fallback: unlisted_companies already in DB for this person (avoids re-scraping).
    Returns de-duplicated list preserving yaml order.
    """
    seeds = list(actor_seeds.get(person_name, []))

    # Also include any companies already scraped that aren't in yaml
    async with get_session() as session:
        result = await session.execute(
            select(UnlistedCompany.name)
            .join(PersonUnlistedRole, PersonUnlistedRole.unlisted_company_id == UnlistedCompany.id)
            .join(Person, Person.id == PersonUnlistedRole.person_id)
            .where(Person.full_name == person_name)
        )
        db_names = [r[0] for r in result.all()]

    # Merge, keeping yaml order first
    seen = set(seeds)
    for name in db_names:
        if name not in seen:
            seeds.append(name)
            seen.add(name)

    return seeds
