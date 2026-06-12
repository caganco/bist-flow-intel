"""Sell-side disclosure event windows — DIAGNOSTIC ONLY.

The portfolio is long-only / no-short by invariant, so insider SELL disclosures
are NEVER trade candidates. These event windows exist solely to make the
buy-vs-sell post-disclosure return *asymmetry* measurable: they let the same
look-ahead-safe return harness be applied to the sell side for description, not
for trading.

Unlike the buy-side ``detect_clusters`` (which requires >= N distinct insiders
in a look-back window), sell-side events are deliberately NOT clustered: each KAP
disclosure that reports one or more SELL transactions is one event. Clustering is
unnecessary for a descriptive asymmetry diagnostic. The differing event
definitions (buy = multi-insider cluster vs sell = per-disclosure) must be
controlled for when the descriptive comparison is computed downstream.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trailing_edge.models.kap import KapInsiderTransaction


@dataclass(frozen=True)
class SellSideEvent:
    """A single sell-side disclosure event. DIAGNOSTIC; never a trade candidate."""

    ticker: str
    disclosure_id: int
    window_start: date  # earliest SELL transaction_date in the disclosure
    window_end: date  # latest SELL transaction_date in the disclosure
    insiders: tuple[str, ...]
    insider_count: int
    total_sell_value_try: Decimal | None


@dataclass(frozen=True)
class SellTxRow:
    """Minimal projection of a SELL transaction for grouping (pure-testable)."""

    disclosure_id: int
    ticker: str
    transaction_date: date
    insider_name: str
    total_value_try: Decimal | None


def group_sell_side_events(rows: Iterable[SellTxRow]) -> list[SellSideEvent]:
    """Group SELL transaction rows into one event per (ticker, disclosure_id).

    Pure function (no DB): callers fetch the rows; this groups them. Insiders are
    de-duplicated order-preserving; ``total_sell_value_try`` sums non-null values
    (None only when every row in the group lacks a value). Output is sorted by
    (ticker, window_end, disclosure_id) for deterministic results.
    """
    buckets: dict[tuple[str, int], list[SellTxRow]] = {}
    for r in rows:
        buckets.setdefault((r.ticker, r.disclosure_id), []).append(r)

    events: list[SellSideEvent] = []
    for (ticker, disclosure_id), grp in buckets.items():
        dates = [r.transaction_date for r in grp]
        insiders = tuple(dict.fromkeys(r.insider_name for r in grp))
        values = [r.total_value_try for r in grp if r.total_value_try is not None]
        total = sum(values, Decimal("0")) if values else None
        events.append(
            SellSideEvent(
                ticker=ticker,
                disclosure_id=disclosure_id,
                window_start=min(dates),
                window_end=max(dates),
                insiders=insiders,
                insider_count=len(insiders),
                total_sell_value_try=total,
            )
        )

    events.sort(key=lambda e: (e.ticker, e.window_end, e.disclosure_id))
    return events


async def build_sell_side_events(
    session: AsyncSession,
    as_of_date: date | None = None,
) -> list[SellSideEvent]:
    """Fetch SELL transactions and group them into diagnostic event windows.

    DIAGNOSTIC ONLY — long-only invariant: these are never trade candidates. The
    look-ahead-safe signal date for each event is its disclosure's
    ``published_at`` (resolved by the same entry-timing helper the buy-side
    harness uses); the descriptive return computation is intentionally NOT
    performed here (it belongs to the deferred measurement step).
    """
    stmt = select(
        KapInsiderTransaction.disclosure_id,
        KapInsiderTransaction.ticker,
        KapInsiderTransaction.transaction_date,
        KapInsiderTransaction.insider_name,
        KapInsiderTransaction.total_value_try,
    ).where(KapInsiderTransaction.transaction_type == "SELL")
    if as_of_date is not None:
        stmt = stmt.where(KapInsiderTransaction.transaction_date <= as_of_date)

    rows = [
        SellTxRow(
            disclosure_id=row.disclosure_id,
            ticker=row.ticker,
            transaction_date=row.transaction_date,
            insider_name=row.insider_name,
            total_value_try=row.total_value_try,
        )
        for row in (await session.execute(stmt)).all()
    ]
    return group_sell_side_events(rows)
