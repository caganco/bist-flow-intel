"""NetworkX company network engine — build graph, find clusters, score them."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from itertools import combinations

import networkx as nx
from sqlalchemy import func, select, text

from flow_intel.core.db import get_session
from flow_intel.core.logging import get_logger
from flow_intel.models.kap import KapInsiderTransaction
from flow_intel.models.signal import InsiderCluster

_log = get_logger(__name__)


@dataclass
class NetworkCluster:
    companies: list[str]
    shared_persons: list[str]
    total_interlock_weight: int
    active_signals: list[dict]
    net_pressure: str               # "NET_BUY" | "NET_SELL" | "NEUTRAL" | "NONE"
    network_alpha_score: float
    as_of_date: date


async def build_company_graph(tickers: list[str] | None = None) -> nx.Graph:
    """Build an undirected graph from board_interlocks.

    Node: ticker string.
    Edge attributes: weight (shared person count), shared_persons, roles_a, roles_b.
    tickers: when given, restrict to edges involving at least one of these tickers.
    """
    base_sql = """
        SELECT company_a, company_b,
               COUNT(*)                AS weight,
               array_agg(person_name)  AS persons,
               array_agg(role_in_a)    AS roles_a,
               array_agg(role_in_b)    AS roles_b
        FROM board_interlocks
        {where}
        GROUP BY company_a, company_b
    """
    if tickers:
        where = "WHERE company_a = ANY(:tickers) OR company_b = ANY(:tickers)"
        params: dict = {"tickers": tickers}
    else:
        where = ""
        params = {}

    G: nx.Graph = nx.Graph()
    async with get_session() as session:
        rows = (await session.execute(text(base_sql.format(where=where)), params)).all()

    for row in rows:
        G.add_edge(
            row.company_a,
            row.company_b,
            weight=row.weight,
            shared_persons=list(row.persons),
            roles_a=list(row.roles_a),
            roles_b=list(row.roles_b),
        )

    _log.info("graph_built", nodes=G.number_of_nodes(), edges=G.number_of_edges())
    return G


def find_interlock_clusters(
    G: nx.Graph,
    min_companies: int = 2,
) -> list[list[str]]:
    """Return connected components with ≥ min_companies nodes, sorted by size DESC."""
    return sorted(
        [sorted(c) for c in nx.connected_components(G) if len(c) >= min_companies],
        key=len,
        reverse=True,
    )


def compute_network_alpha_score(
    active_signals: list[dict],
    total_interlock_weight: int,
    net_pressure: str,
) -> float:
    """Composite score in range [0.0, 100.0].

    Component 1 (50p): max cluster_score from active signals.
    Component 2 (30p): interlock density, saturates at 5 shared persons.
    Component 3 (20p): net buy pressure (NET_SELL=0, NONE=0.3, NEUTRAL=0.5, NET_BUY=1.0).
    """
    signal_score = (
        max(float(s["cluster_score"]) for s in active_signals) / 100.0
        if active_signals
        else 0.0
    )
    interlock_score = min(total_interlock_weight / 5.0, 1.0)
    pressure_map = {"NET_BUY": 1.0, "NEUTRAL": 0.5, "NONE": 0.3, "NET_SELL": 0.0}
    pressure_score = pressure_map.get(net_pressure, 0.0)

    return round(
        signal_score * 50.0 + interlock_score * 30.0 + pressure_score * 20.0,
        2,
    )


async def enrich_cluster_with_signals(
    G: nx.Graph,
    company_group: list[str],
    as_of_date: date | None = None,
) -> NetworkCluster:
    """Enrich an interlock cluster with insider signal data and net buy pressure."""
    today = as_of_date or date.today()

    shared_persons: set[str] = set()
    total_interlock_weight = 0
    for a, b in combinations(company_group, 2):
        if G.has_edge(a, b):
            edge = G[a][b]
            shared_persons.update(edge.get("shared_persons", []))
            total_interlock_weight += edge.get("weight", 1)

    async with get_session() as session:
        # Best cluster per ticker (highest score) to avoid double-counting overlapping windows
        rows = (
            await session.execute(
                text("""
                    SELECT DISTINCT ON (ticker)
                        ticker, window_start, window_end, cluster_score,
                        insider_count, unique_insiders, total_buy_value_try
                    FROM insider_clusters
                    WHERE ticker = ANY(:tickers)
                    ORDER BY ticker, cluster_score DESC
                """),
                {"tickers": list(company_group)},
            )
        ).all()

        active_signals = [
            {
                "ticker": r.ticker,
                "cluster_score": float(r.cluster_score),
                "insider_count": r.insider_count,
                "window_start": r.window_start,
                "window_end": r.window_end,
                "unique_insiders": list(r.unique_insiders or []),
                "total_buy_value_try": float(r.total_buy_value_try) if r.total_buy_value_try else None,
            }
            for r in rows
        ]

        total_buy = Decimal(0)
        total_sell = Decimal(0)
        for sig in active_signals:
            pressure_rows = (
                await session.execute(
                    select(
                        KapInsiderTransaction.transaction_type,
                        func.sum(KapInsiderTransaction.share_count).label("total"),
                    )
                    .where(
                        KapInsiderTransaction.ticker == sig["ticker"],
                        KapInsiderTransaction.transaction_date >= sig["window_start"],
                        KapInsiderTransaction.transaction_date <= sig["window_end"],
                    )
                    .group_by(KapInsiderTransaction.transaction_type)
                )
            ).all()
            for pr in pressure_rows:
                if pr.transaction_type == "BUY":
                    total_buy += pr.total or Decimal(0)
                else:
                    total_sell += pr.total or Decimal(0)

    if not active_signals:
        net_pressure = "NONE"
    elif total_buy > total_sell:
        net_pressure = "NET_BUY"
    elif total_sell > total_buy:
        net_pressure = "NET_SELL"
    else:
        net_pressure = "NEUTRAL"

    score = compute_network_alpha_score(active_signals, total_interlock_weight, net_pressure)

    return NetworkCluster(
        companies=sorted(company_group),
        shared_persons=sorted(shared_persons),
        total_interlock_weight=total_interlock_weight,
        active_signals=active_signals,
        net_pressure=net_pressure,
        network_alpha_score=score,
        as_of_date=today,
    )
