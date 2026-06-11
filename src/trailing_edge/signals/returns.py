"""Forward return calculation for insider clusters."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.dialects.postgresql import insert as pg_insert

from trailing_edge.core.db import get_session
from trailing_edge.core.logging import get_logger
from trailing_edge.data.prices import get_price_after_days, get_price_on_date
from trailing_edge.models.signal import InsiderCluster, SignalOutcome

_log = get_logger(__name__)


async def calculate_outcomes(
    clusters: list[InsiderCluster],
    horizons: list[int],
) -> None:
    """
    For each cluster × horizon, calculate forward return and upsert to signal_outcomes.

    entry_price = close on cluster.window_end (or nearest prior trading day)
    exit_price  = close exactly horizon trading days after window_end
    return_pct  = (exit - entry) / entry * 100

    exit_price=None when the horizon date is in the future or price data is missing.
    All operations share one session to avoid repeated connection acquisition.
    """
    async with get_session() as session:
        for cluster in clusters:
            entry_price = await get_price_on_date(
                cluster.ticker, cluster.window_end, session=session
            )

            for horizon in horizons:
                exit_price: Decimal | None = None
                return_pct: Decimal | None = None

                if entry_price is not None:
                    exit_price = await get_price_after_days(
                        cluster.ticker, cluster.window_end, horizon, session=session
                    )
                    if exit_price is not None and entry_price > 0:
                        return_pct = (
                            (exit_price - entry_price) / entry_price * Decimal("100")
                        ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

                stmt = (
                    pg_insert(SignalOutcome.__table__)
                    .values(
                        cluster_id=cluster.id,
                        horizon_days=horizon,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        return_pct=return_pct,
                    )
                    .on_conflict_do_update(
                        constraint="uq_outcome_cluster_horizon",
                        set_={
                            "entry_price": entry_price,
                            "exit_price": exit_price,
                            "return_pct": return_pct,
                        },
                    )
                )
                await session.execute(stmt)

                _log.info(
                    "outcome_upserted",
                    ticker=cluster.ticker,
                    window_end=str(cluster.window_end),
                    horizon=horizon,
                    return_pct=float(return_pct) if return_pct is not None else None,
                )
