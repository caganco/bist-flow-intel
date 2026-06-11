"""Network analysis report - stdout table + JSON file."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import click

from trailing_edge.core.logging import get_logger
from trailing_edge.signals.graph import (
    NetworkCluster,
    build_company_graph,
    enrich_cluster_with_signals,
    find_interlock_clusters,
)

_log = get_logger(__name__)


@dataclass
class NetworkReport:
    as_of_date: date
    clusters: list[NetworkCluster]
    report_path: Path


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


def _print_network_table(as_of_date: date, clusters: list[NetworkCluster]) -> None:
    col_companies = max(14, max(len(" · ".join(c.companies)) for c in clusters))
    col_score = 8
    col_persons = 9
    col_pressure = 12
    col_signals = max(16, max(
        len(", ".join(f"{s['ticker']}={s['cluster_score']:.1f}" for s in c.active_signals) or "-")
        for c in clusters
    ))

    sep = (
        "+"
        + "-" * col_companies
        + "+"
        + "-" * col_score
        + "+"
        + "-" * col_persons
        + "+"
        + "-" * col_pressure
        + "+"
        + "-" * col_signals
        + "+"
    )

    title = f" TrailingEdge  NETWORK ANALYSIS  {as_of_date} "
    title_width = len(sep) - 2
    click.echo("+" + "-" * title_width + "+")
    click.echo("|" + title.center(title_width) + "|")
    click.echo(sep)
    click.echo(
        "|"
        + " COMPANIES".ljust(col_companies)
        + "|"
        + " SCORE".ljust(col_score)
        + "|"
        + " PERSONS".ljust(col_persons)
        + "|"
        + " PRESSURE".ljust(col_pressure)
        + "|"
        + " ACTIVE SIGNALS".ljust(col_signals)
        + "|"
    )
    click.echo(sep)

    for nc in clusters:
        companies_str = " · ".join(nc.companies)
        score_str = f"{nc.network_alpha_score:.2f}"
        pressure_str = nc.net_pressure + (" (!)" if nc.net_pressure == "NET_SELL" else "")
        signals_str = (
            ", ".join(f"{s['ticker']}={s['cluster_score']:.1f}" for s in nc.active_signals)
            if nc.active_signals
            else "-"
        )
        click.echo(
            "|"
            + f" {companies_str}".ljust(col_companies)
            + "|"
            + f" {score_str}".ljust(col_score)
            + "|"
            + f" {nc.total_interlock_weight}".ljust(col_persons)
            + "|"
            + f" {pressure_str}".ljust(col_pressure)
            + "|"
            + f" {signals_str}".ljust(col_signals)
            + "|"
        )

    click.echo(sep)


async def generate_network_report(
    as_of_date: date | None = None,
    min_alpha_score: float = 0.0,
) -> NetworkReport:
    """Build graph → find clusters → enrich → sort by score → stdout + JSON."""
    today = as_of_date or date.today()

    G = await build_company_graph()
    groups = find_interlock_clusters(G)

    enriched: list[NetworkCluster] = []
    for group in groups:
        nc = await enrich_cluster_with_signals(G, group, as_of_date=today)
        if nc.network_alpha_score >= min_alpha_score:
            enriched.append(nc)

    enriched.sort(key=lambda c: c.network_alpha_score, reverse=True)

    if enriched:
        _print_network_table(today, enriched)
    else:
        click.echo(f"No network clusters above score {min_alpha_score} as of {today}.")

    reports_dir = Path("reports") / "network"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{today}_network_intel.json"

    payload = _to_json_safe({
        "as_of_date": today,
        "cluster_count": len(enriched),
        "clusters": [
            {
                "companies": nc.companies,
                "shared_persons": nc.shared_persons,
                "total_interlock_weight": nc.total_interlock_weight,
                "net_pressure": nc.net_pressure,
                "network_alpha_score": nc.network_alpha_score,
                "active_signals": nc.active_signals,
            }
            for nc in enriched
        ],
        "generated_at": today,
    })
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _log.info("network_report_written", path=str(report_path), cluster_count=len(enriched))

    return NetworkReport(as_of_date=today, clusters=enriched, report_path=report_path)
