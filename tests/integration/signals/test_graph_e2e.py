"""Integration tests for NetworkX graph engine — requires live DB."""
import networkx as nx
import pytest

pytestmark = pytest.mark.asyncio


async def test_build_graph_from_db(db_session):
    """board_interlocks'tan graph insa edilebiliyor, crash yok."""
    from flow_intel.signals.graph import build_company_graph

    G = await build_company_graph()
    assert isinstance(G, nx.Graph)
    assert G.number_of_edges() > 0


async def test_network_report_generates_file(db_session, tmp_path, monkeypatch):
    """generate_network_report calisiyor, JSON dosyasi olusturuluyor."""
    monkeypatch.chdir(tmp_path)
    from flow_intel.reports.network_report import generate_network_report

    report = await generate_network_report()
    assert report.report_path.exists()
    assert isinstance(report.clusters, list)


async def test_net_pressure_kaplm(db_session):
    """KAPLM icin net_pressure hesaplanabiliyor."""
    from flow_intel.signals.graph import build_company_graph, enrich_cluster_with_signals

    G = await build_company_graph()
    if "KAPLM" not in G:
        pytest.skip("KAPLM has no interlocks in this DB state")

    neighbors = list(G.neighbors("KAPLM"))
    nc = await enrich_cluster_with_signals(G, ["KAPLM"] + neighbors[:1])
    assert nc.net_pressure in ("NET_BUY", "NET_SELL", "NEUTRAL", "NONE")
    assert isinstance(nc.network_alpha_score, float)
    assert 0.0 <= nc.network_alpha_score <= 100.0
