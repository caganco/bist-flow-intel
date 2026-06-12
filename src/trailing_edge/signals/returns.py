"""Forward return calculation for insider clusters."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.dialects.postgresql import insert as pg_insert

from trailing_edge.core.db import get_session
from trailing_edge.core.logging import get_logger
from trailing_edge.data.prices import get_price_after_days
from trailing_edge.models.signal import InsiderCluster, SignalOutcome
from trailing_edge.signals.entry_timing import (
    ENTRY_OFFSET_TRADING_DAYS,
    entry_exit_offsets,
    resolve_cluster_signal_dates,
)

_log = get_logger(__name__)


async def calculate_outcomes(
    clusters: list[InsiderCluster],
    horizons: list[int],
) -> None:
    """
    For each cluster × horizon, calculate the look-ahead-safe forward return and
    upsert to signal_outcomes.

    Entry is keyed to the look-ahead-safe *signal date* — the latest public KAP
    disclosure (``published_at``, correction-aware) backing the cluster — NOT the
    private transaction ``window_end``. This removes the filing-lag look-ahead:
      entry_price = close on t+1 (first trading day after the signal date)
      exit_price  = close ``horizon`` trading days after entry
      return_pct  = (exit - entry) / entry * 100

    Clusters with no resolvable public disclosure are skipped (cannot be entered
    look-ahead-safely). A signal date earlier than ``window_end`` is impossible
    for valid data (a disclosure cannot predate the transactions it reports) and
    is treated as a hard look-ahead violation. exit_price=None when the horizon
    date is in the future or price data is missing. All operations share one
    session to avoid repeated connection acquisition.
    """
    async with get_session() as session:
        signal_dates = await resolve_cluster_signal_dates(clusters, session)

        for cluster in clusters:
            signal_date = signal_dates.get(cluster.id)
            if signal_date is None:
                _log.warning(
                    "outcome_skipped_no_public_disclosure",
                    ticker=cluster.ticker,
                    window_end=str(cluster.window_end),
                )
                continue

            # Look-ahead guard: the public disclosure cannot predate the last
            # transaction it reports, so the signal date must be on/after
            # window_end. A violation means malformed data — fail loud rather
            # than silently emit a look-ahead-biased return.
            if signal_date < cluster.window_end:
                raise AssertionError(
                    f"look-ahead violation: signal_date {signal_date} < window_end "
                    f"{cluster.window_end} for {cluster.ticker}"
                )

            # Entry strictly AFTER the public-disclosure day (t+1).
            entry_price = await get_price_after_days(
                cluster.ticker, signal_date, ENTRY_OFFSET_TRADING_DAYS, session=session
            )

            for horizon in horizons:
                exit_price: Decimal | None = None
                return_pct: Decimal | None = None

                if entry_price is not None:
                    _, exit_offset = entry_exit_offsets(horizon)
                    exit_price = await get_price_after_days(
                        cluster.ticker, signal_date, exit_offset, session=session
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
                    signal_date=str(signal_date),
                    window_end=str(cluster.window_end),
                    horizon=horizon,
                    return_pct=float(return_pct) if return_pct is not None else None,
                )
