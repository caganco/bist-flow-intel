"""Ranked daily insider cluster signal report — stdout table + JSON file."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import click

from flow_intel.core.config import get_config
from flow_intel.core.logging import get_logger
from flow_intel.models.signal import InsiderCluster
from flow_intel.signals.base_rate import BaseRateStats, compute_base_rate
from flow_intel.signals.cluster import detect_clusters
from flow_intel.signals.returns import calculate_outcomes

_log = get_logger(__name__)


@dataclass
class DailyReport:
    as_of_date: date
    clusters: list[InsiderCluster]
    base_rates: dict[int, BaseRateStats]  # key: horizon_days
    report_path: Path


def _fmt_pct(v: Decimal | None) -> str:
    return f"{v:.1f}%" if v is not None else "n/a"


def _print_table(as_of_date: date, clusters: list[InsiderCluster], base_rates: dict[int, BaseRateStats]) -> None:
    horizons = sorted(base_rates)
    header_hr = "  ".join(f"{h}d:{_fmt_pct(base_rates[h].hit_rate_pct)}" for h in horizons)

    col_w = {
        "ticker": max(6, max((len(c.ticker) for c in clusters), default=6)),
        "score": 7,
        "insiders": 9,
        "days": 6,
    }
    hr_w = max(20, len(header_hr) + 2)

    sep_row = (
        "+"
        + "-" * col_w["ticker"]
        + "+"
        + "-" * col_w["score"]
        + "+"
        + "-" * col_w["insiders"]
        + "+"
        + "-" * col_w["days"]
        + "+"
        + "-" * hr_w
        + "+"
    )

    title = f" FLOW-INTEL  INSIDER CLUSTER SIGNAL  {as_of_date} "
    title_width = len(sep_row) - 2
    click.echo("+" + "-" * title_width + "+")
    click.echo("|" + title.center(title_width) + "|")
    click.echo(sep_row)
    click.echo(
        "|"
        + " TICKER".ljust(col_w["ticker"])
        + "|"
        + " SCORE".ljust(col_w["score"])
        + "|"
        + " INSIDERS".ljust(col_w["insiders"])
        + "|"
        + " DAYS".ljust(col_w["days"])
        + "|"
        + " HIST. HIT RATE".ljust(hr_w)
        + "|"
    )
    click.echo(sep_row)

    for c in clusters:
        days_since = (as_of_date - c.window_end).days
        score_str = f"{float(c.cluster_score):.1f}"
        hit_str = "  ".join(f"{h}d:{_fmt_pct(base_rates[h].hit_rate_pct)}" for h in horizons)
        click.echo(
            "|"
            + f" {c.ticker}".ljust(col_w["ticker"])
            + "|"
            + f" {score_str}".ljust(col_w["score"])
            + "|"
            + f" {c.insider_count}".ljust(col_w["insiders"])
            + "|"
            + f" {days_since}".ljust(col_w["days"])
            + "|"
            + f" {hit_str}".ljust(hr_w)
            + "|"
        )

    click.echo(sep_row)


def _to_json_safe(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, date):
        return str(obj)
    if isinstance(obj, list):
        return [_to_json_safe(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    return obj


async def generate_daily_report(as_of_date: date | None = None) -> DailyReport:
    """
    1. detect_clusters(as_of_date) — upsert all relevant cluster events
    2. calculate_outcomes(clusters, horizons) — fill forward returns
    3. compute_base_rate per horizon — ticker-agnostic historical accuracy
    4. Sort clusters by cluster_score DESC
    5. Print stdout table
    6. Write reports/daily/{YYYY-MM-DD}_signal.json
    """
    today = as_of_date or date.today()
    cfg = get_config()["signals"]
    horizons: list[int] = cfg["returns"]["horizons"]

    clusters = await detect_clusters(as_of_date=today)
    await calculate_outcomes(clusters, horizons)

    base_rates: dict[int, BaseRateStats] = {}
    for h in horizons:
        base_rates[h] = await compute_base_rate(h)

    # Sort by cluster_score DESC
    clusters_sorted = sorted(clusters, key=lambda c: c.cluster_score, reverse=True)

    if clusters_sorted:
        _print_table(today, clusters_sorted, base_rates)
    else:
        print(f"No active clusters as of {today}.")

    # Write JSON
    reports_dir = Path("reports") / "daily"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{today}_signal.json"

    payload = {
        "as_of_date": str(today),
        "clusters": [
            {
                "ticker": c.ticker,
                "cluster_score": float(c.cluster_score),
                "insider_count": c.insider_count,
                "window_start": str(c.window_start),
                "window_end": str(c.window_end),
                "days_since_last_buy": (today - c.window_end).days,
                "unique_insiders": c.unique_insiders,
                "total_buy_value_try": float(c.total_buy_value_try) if c.total_buy_value_try else None,
            }
            for c in clusters_sorted
        ],
        "base_rates": {
            str(h): {
                "horizon_days": h,
                "total_signals": base_rates[h].total_signals,
                "signals_with_outcome": base_rates[h].signals_with_outcome,
                "hit_rate_pct": float(base_rates[h].hit_rate_pct),
                "median_return_pct": float(base_rates[h].median_return_pct),
                "avg_return_pct": float(base_rates[h].avg_return_pct),
                "best_return_pct": float(base_rates[h].best_return_pct),
                "worst_return_pct": float(base_rates[h].worst_return_pct),
            }
            for h in horizons
        },
        "generated_at": str(today),
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _log.info("daily_report_written", path=str(report_path), cluster_count=len(clusters_sorted))

    return DailyReport(
        as_of_date=today,
        clusters=clusters_sorted,
        base_rates=base_rates,
        report_path=report_path,
    )
