"""Unit tests for forensic report — pure functions, no DB."""
import base64
from datetime import date

import networkx as nx
import pytest

from flow_intel.reports.forensic_report import (
    ForensicReportData,
    generate_html_report,
    render_network_graph_png,
)
from flow_intel.signals.graph import NetworkCluster


@pytest.fixture
def mock_forensic_data():
    cluster = NetworkCluster(
        companies=["KAPLM", "RALYH"],
        shared_persons=["RİZA KANDEMİR"],
        total_interlock_weight=1,
        active_signals=[],
        net_pressure="NONE",
        network_alpha_score=6.0,
        as_of_date=date(2025, 10, 31),
    )
    return ForensicReportData(
        ticker="KAPLM",
        company_name="Kaplamin Ambalaj Sanayi ve Ticaret A.Ş.",
        report_date=date(2025, 10, 31),
        network_cluster=cluster,
        transactions=[
            {
                "insider_name": "RİZA KANDEMİR",
                "insider_role": "YK BAŞKANI",
                "transaction_date": date(2025, 10, 31),
                "transaction_type": "BUY",
                "share_count_fmt": "7,003,772",
                "price_try_fmt": "—",
                "post_tx_pct_fmt": "—",
            }
        ],
        board_connections=[
            {
                "company_a": "KAPLM",
                "company_b": "RALYH",
                "person_name": "RİZA KANDEMİR",
                "role_in_a": "YK BAŞKANI",
                "role_in_b": "YK ÜYESİ",
            }
        ],
        graph_png_b64=base64.b64encode(b"FAKE_PNG").decode(),
    )


def test_render_network_graph_png_returns_bytes():
    """render produces non-empty PNG bytes, no crash."""
    G = nx.Graph()
    G.add_edge("KAPLM", "RALYH", weight=2, shared_persons=["RİZA KANDEMİR"], roles_a=[], roles_b=[])
    result = render_network_graph_png("KAPLM", G, ["KAPLM", "RALYH"])
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_html_contains_required_sections(mock_forensic_data):
    """Rendered HTML has all 4 structural sections."""
    html = generate_html_report(mock_forensic_data)
    assert "CONFIDENTIAL" in html
    assert "Composite Anomaly Score" in html
    assert "Yönetim Kurulu" in html
    assert "Koordineli" in html


def test_buy_sell_display_labels(mock_forensic_data):
    """BUY transaction_type renders as 'Alım' in HTML."""
    html = generate_html_report(mock_forensic_data)
    assert "Alım" in html
