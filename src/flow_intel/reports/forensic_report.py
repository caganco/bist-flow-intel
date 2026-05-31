"""Corporate Forensic Intelligence Brief — HTML + PDF export."""
from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

logging.getLogger("matplotlib").setLevel(logging.WARNING)
logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)

import jinja2
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend — must precede pyplot import
import matplotlib.pyplot as plt
import networkx as nx
from sqlalchemy import select, text

from flow_intel.core.db import get_session
from flow_intel.core.logging import get_logger
from flow_intel.models.graph import Company, Person
from flow_intel.models.kap import KapInsiderTransaction
from flow_intel.signals.graph import NetworkCluster, build_company_graph, enrich_cluster_with_signals

_log = get_logger(__name__)
_TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class ForensicReportData:
    ticker: str
    company_name: str
    report_date: date
    network_cluster: NetworkCluster
    transactions: list[dict]
    board_connections: list[dict]
    graph_png_b64: str
    actor_footprints: list = field(default_factory=list)    # list[ActorFootprint]
    unknown_associates: list = field(default_factory=list)  # raw_person_name, company_name, role
    related_party_findings: list = field(default_factory=list)  # list[RelatedPartyFinding]
    tender_findings: list = field(default_factory=list)         # list[TenderFinding]
    management_bridges: list = field(default_factory=list)      # {person, listed, unlisted}


async def gather_report_data(ticker: str, report_date: date | None = None) -> ForensicReportData:
    today = report_date or date.today()

    async with get_session() as session:
        result = await session.execute(
            select(Company.company_name).where(Company.ticker == ticker).limit(1)
        )
        company_name = result.scalar_one_or_none() or ticker

        tx_rows = (
            await session.execute(
                select(KapInsiderTransaction)
                .where(KapInsiderTransaction.ticker == ticker)
                .order_by(KapInsiderTransaction.transaction_date.desc())
                .limit(50)
            )
        ).scalars().all()

        transactions = [
            {
                "insider_name": tx.insider_name,
                "insider_role": tx.insider_role,
                "transaction_date": tx.transaction_date,
                "transaction_type": tx.transaction_type,
                "share_count_fmt": f"{float(tx.share_count):,.0f}" if tx.share_count is not None else "—",
                "price_try_fmt": f"{float(tx.price_try):.4f}" if tx.price_try is not None else "—",
                "post_tx_pct_fmt": f"{float(tx.post_tx_ownership_pct):.2f}" if tx.post_tx_ownership_pct is not None else "—",
            }
            for tx in tx_rows
        ]

        conn_rows = (
            await session.execute(
                text("""
                    SELECT company_a, company_b, person_name, role_in_a, role_in_b
                    FROM board_interlocks
                    WHERE company_a = :ticker OR company_b = :ticker
                    ORDER BY person_name
                """),
                {"ticker": ticker},
            )
        ).all()

        board_connections = [
            {
                "company_a": row.company_a,
                "company_b": row.company_b,
                "person_name": row.person_name,
                "role_in_a": row.role_in_a,
                "role_in_b": row.role_in_b,
            }
            for row in conn_rows
        ]

    G = await build_company_graph()
    if ticker in G:
        cluster_tickers = [ticker] + list(G.neighbors(ticker))[:3]
    else:
        cluster_tickers = [ticker]
    network_cluster = await enrich_cluster_with_signals(G, cluster_tickers, as_of_date=today)

    png_bytes = render_network_graph_png(ticker, G, network_cluster.companies)
    graph_png_b64 = base64.b64encode(png_bytes).decode()

    actor_footprints, unknown_associates = await _gather_tsg_layer(network_cluster.shared_persons)

    from flow_intel.signals.financial_flow import (
        build_management_bridges,
        fetch_related_party_disclosures,
    )
    related_party_findings = await fetch_related_party_disclosures(ticker)
    management_bridges = build_management_bridges(actor_footprints)

    return ForensicReportData(
        ticker=ticker,
        company_name=company_name,
        report_date=today,
        network_cluster=network_cluster,
        transactions=transactions,
        board_connections=board_connections,
        graph_png_b64=graph_png_b64,
        actor_footprints=actor_footprints,
        unknown_associates=unknown_associates,
        related_party_findings=related_party_findings,
        tender_findings=[],
        management_bridges=management_bridges,
    )


async def _gather_tsg_layer(shared_persons: list[str]) -> tuple[list, list]:
    """Map cluster board members to person_ids, collect their TSG footprints.

    Returns (actor_footprints, unknown_associates) where unknown_associates is
    the deduplicated union of unmatched people sharing those actors' companies.
    """
    from flow_intel.scrapers.kap.helpers import normalize_name
    from flow_intel.signals.cross_reference import get_actor_footprint

    if not shared_persons:
        return [], []

    norm_targets = {normalize_name(p) for p in shared_persons}
    async with get_session() as session:
        persons = (await session.execute(select(Person))).scalars().all()
    person_ids = [p.id for p in persons if p.name_normalized in norm_targets]

    footprints = [await get_actor_footprint(pid) for pid in person_ids]
    footprints = [fp for fp in footprints if fp.unlisted_companies]

    seen: set[tuple[str, str]] = set()
    unknown_associates: list[dict] = []
    for fp in footprints:
        for assoc in fp.unknown_associates:
            key = (assoc["raw_person_name"], assoc["company_name"])
            if key not in seen:
                seen.add(key)
                unknown_associates.append(assoc)

    return footprints, unknown_associates


def render_network_graph_png(
    ticker: str,
    G: nx.Graph,
    cluster_companies: list[str],
) -> bytes:
    """NetworkX + matplotlib → PNG bytes. Sync, no DB."""
    relevant: set[str] = set(cluster_companies)
    for t in list(cluster_companies):
        if t in G:
            relevant.update(G.neighbors(t))

    graph_nodes = set(G.nodes())
    subG = G.subgraph(relevant & graph_nodes).copy() if relevant & graph_nodes else nx.Graph()
    if subG.number_of_nodes() == 0:
        subG.add_node(ticker)

    node_list = list(subG.nodes())
    node_colors = [
        "#0A0A0A" if n == ticker else ("#555555" if n in cluster_companies else "#CCCCCC")
        for n in node_list
    ]
    font_colors = {n: "white" if n in cluster_companies or n == ticker else "black" for n in node_list}
    edge_widths = [max(subG[u][v].get("weight", 1) * 1.5, 1.0) for u, v in subG.edges()]

    fig, ax = plt.subplots(figsize=(10, 7))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    pos = nx.spring_layout(subG, seed=42, k=2.5)
    nx.draw_networkx_nodes(subG, pos, ax=ax, node_color=node_colors, node_size=1200)
    for node, (x, y) in pos.items():
        ax.text(
            x, y, node,
            ha="center", va="center",
            fontsize=8, fontweight="bold",
            color=font_colors.get(node, "black"),
        )
    if subG.number_of_edges() > 0:
        nx.draw_networkx_edges(subG, pos, ax=ax, width=edge_widths, edge_color="#888888", alpha=0.7)
        edge_labels: dict = {}
        for u, v in subG.edges():
            persons = subG[u][v].get("shared_persons", [])
            if persons:
                label = persons[0][:20] + ("…" if len(persons[0]) > 20 else "")
                edge_labels[(u, v)] = label
        if edge_labels:
            nx.draw_networkx_edge_labels(
                subG, pos, edge_labels, ax=ax, font_size=6
            )

    ax.set_title(f"Yönetim Kurulu Bağlantı Ağı — {ticker}", fontsize=10, fontweight="bold")
    ax.axis("off")

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", facecolor="white", dpi=150)
    plt.close(fig)
    return buf.getvalue()


def generate_html_report(data: ForensicReportData) -> str:
    """Pure Jinja2 render — sync, no DB."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=True,
    )
    return env.get_template("base.html").render(data=data)


async def generate_pdf_report(html: str, output_path: Path) -> Path:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        await page.pdf(
            path=str(output_path),
            format="A4",
            margin={"top": "2cm", "bottom": "2cm", "left": "2cm", "right": "2cm"},
            print_background=True,
        )
        await browser.close()
    return output_path


async def gather_all_signal_tickers() -> list[str]:
    async with get_session() as session:
        rows = (
            await session.execute(text("SELECT DISTINCT ticker FROM insider_clusters ORDER BY ticker"))
        ).all()
    return [row[0] for row in rows]


async def generate_forensic_report(
    ticker: str,
    output_format: str = "pdf",
    report_date: date | None = None,
) -> Path:
    today = report_date or date.today()
    data = await gather_report_data(ticker, report_date=today)
    html = generate_html_report(data)

    reports_dir = Path("reports") / "forensic"
    reports_dir.mkdir(parents=True, exist_ok=True)

    html_path = reports_dir / f"{today}_{ticker}_forensic_brief.html"
    pdf_path = reports_dir / f"{today}_{ticker}_forensic_brief.pdf"

    if output_format in ("html", "both"):
        html_path.write_text(html, encoding="utf-8")
        _log.info("forensic_html_written", path=str(html_path), ticker=ticker)

    if output_format in ("pdf", "both"):
        await generate_pdf_report(html, pdf_path)
        _log.info("forensic_pdf_written", path=str(pdf_path), ticker=ticker)
        return pdf_path

    return html_path
