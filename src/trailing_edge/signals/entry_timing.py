"""Look-ahead-safe entry timing for disclosure-driven signals.

A KAP insider disclosure is only actionable AFTER it is publicly disclosed
(``published_at``), never on the transaction date the disclosure reports: the
filing lag means the transaction date is private until the filing appears. The
forward-return harness therefore enters at t+1 relative to the *latest* public
disclosure that defines the event — the standard event-study convention of
entering the bar after the public disclosure (e.g. Tahaoglu-Guner 2010).

Correction handling: a corrected disclosure only becomes fully public when the
correction itself is filed, so the look-ahead-safe instant is the LATEST
``published_at`` among the backing disclosure and any disclosure that corrects
it (``corrects_disclosure_id``). ``look_ahead_safe_signal_date`` takes the max,
so a later correction timestamp naturally wins.

Known pipeline caveat (documented, not silently handled): an in-place correction
that re-publishes under the *same* ``disclosureIndex`` does not currently advance
``published_at`` (the upsert leaves it unchanged) and does not populate
``corrects_disclosure_id``. For those, the later public instant cannot be
recovered from stored fields here; advancing ``published_at`` on correction is a
scraper-side fix, not worked around with a non-PIT timestamp (e.g. ingestion
time) in this module.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from trailing_edge.core.time import TR_TZ
from trailing_edge.models.kap import KapDisclosure, KapInsiderTransaction
from trailing_edge.models.signal import InsiderCluster

# t+1 entry: the first trading day STRICTLY AFTER the public-disclosure day.
# Never 0 (the disclosure/transaction day itself), which would be look-ahead.
ENTRY_OFFSET_TRADING_DAYS = 1


def look_ahead_safe_signal_date(published_ats: Iterable[datetime]) -> date:
    """Latest public-disclosure instant, as an Istanbul-local calendar date.

    This is the day from which a t+1 entry is measured. Corrections are simply
    later ``published_at`` values, so ``max`` selects the correction date when
    one exists. ``None`` entries are ignored. Raises ``ValueError`` on empty
    input (a cluster with no backing public disclosure cannot be entered
    look-ahead-safely — the caller must skip it, never fall back to the private
    transaction date).
    """
    latest: datetime | None = None
    for ts in published_ats:
        if ts is None:
            continue
        if latest is None or ts > latest:
            latest = ts
    if latest is None:
        raise ValueError(
            "no published_at timestamps; cannot derive a look-ahead-safe entry date"
        )
    return latest.astimezone(TR_TZ).date()


def entry_exit_offsets(horizon_days: int) -> tuple[int, int]:
    """Trading-day offsets (from the signal date) for entry and exit prices.

    Entry = t+1 (offset 1). Exit = ``horizon_days`` trading days after entry
    (offset ``1 + horizon_days``). Both are measured from the look-ahead-safe
    signal date, never from the private transaction date.
    """
    if horizon_days < 1:
        raise ValueError(f"horizon_days must be >= 1, got {horizon_days}")
    return ENTRY_OFFSET_TRADING_DAYS, ENTRY_OFFSET_TRADING_DAYS + horizon_days


async def resolve_cluster_signal_dates(
    clusters: list[InsiderCluster],
    session: AsyncSession,
) -> dict[int, date]:
    """Map each cluster id -> look-ahead-safe signal date (max ``published_at``).

    For each cluster, gather the disclosures backing its in-window BUY
    transactions, plus any disclosure that *corrects* one of them
    (``corrects_disclosure_id``), and take the latest ``published_at``. Clusters
    whose backing disclosures are missing or unstamped are omitted from the map;
    the caller must skip them rather than fall back to a look-ahead-unsafe
    transaction date.

    DB-backed; the pure decision logic it delegates to
    (``look_ahead_safe_signal_date``) is unit-tested without a database.
    """
    out: dict[int, date] = {}
    for cluster in clusters:
        backing_ids = (
            select(KapInsiderTransaction.disclosure_id)
            .where(
                KapInsiderTransaction.ticker == cluster.ticker,
                KapInsiderTransaction.transaction_type == "BUY",
                KapInsiderTransaction.transaction_date >= cluster.window_start,
                KapInsiderTransaction.transaction_date <= cluster.window_end,
            )
            .scalar_subquery()
        )
        stmt = select(KapDisclosure.published_at).where(
            or_(
                KapDisclosure.id.in_(backing_ids),
                KapDisclosure.corrects_disclosure_id.in_(backing_ids),
            )
        )
        published_ats = [
            ts for ts in (await session.execute(stmt)).scalars().all() if ts is not None
        ]
        if not published_ats:
            continue
        out[cluster.id] = look_ahead_safe_signal_date(published_ats)
    return out
