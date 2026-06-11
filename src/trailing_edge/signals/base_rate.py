"""Historical accuracy (base rate) statistics for insider cluster signals."""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select

from trailing_edge.core.db import get_session
from trailing_edge.models.signal import InsiderCluster, SignalOutcome


@dataclass
class BaseRateStats:
    horizon_days: int
    total_signals: int
    signals_with_outcome: int
    hit_rate_pct: Decimal
    median_return_pct: Decimal
    avg_return_pct: Decimal
    best_return_pct: Decimal
    worst_return_pct: Decimal


_ZERO = Decimal("0.00")


async def compute_base_rate(
    horizon_days: int,
    min_cluster_score: float = 0.0,
) -> BaseRateStats:
    """
    Compute historical accuracy stats for clusters with score >= min_cluster_score.

    total_signals:         rows in signal_outcomes for this horizon (incl. null return_pct)
    signals_with_outcome:  rows with non-null return_pct (price data available)
    hit_rate_pct:          fraction of positive returns × 100
    median/avg/best/worst: computed Python-side from return_pct values
    """
    min_score = Decimal(str(min_cluster_score))

    async with get_session() as session:
        stmt = (
            select(SignalOutcome.return_pct)
            .join(InsiderCluster, InsiderCluster.id == SignalOutcome.cluster_id)
            .where(
                SignalOutcome.horizon_days == horizon_days,
                InsiderCluster.cluster_score >= min_score,
            )
        )
        all_rows = (await session.execute(stmt)).scalars().all()

    total_signals = len(all_rows)
    return_pcts = [Decimal(str(r)) for r in all_rows if r is not None]
    signals_with_outcome = len(return_pcts)

    if not return_pcts:
        return BaseRateStats(
            horizon_days=horizon_days,
            total_signals=total_signals,
            signals_with_outcome=0,
            hit_rate_pct=_ZERO,
            median_return_pct=_ZERO,
            avg_return_pct=_ZERO,
            best_return_pct=_ZERO,
            worst_return_pct=_ZERO,
        )

    floats = [float(r) for r in return_pcts]
    hits = sum(1 for r in return_pcts if r > 0)

    def _dec(v: float) -> Decimal:
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return BaseRateStats(
        horizon_days=horizon_days,
        total_signals=total_signals,
        signals_with_outcome=signals_with_outcome,
        hit_rate_pct=_dec(hits / signals_with_outcome * 100),
        median_return_pct=_dec(statistics.median(floats)),
        avg_return_pct=_dec(sum(floats) / len(floats)),
        best_return_pct=_dec(max(floats)),
        worst_return_pct=_dec(min(floats)),
    )
