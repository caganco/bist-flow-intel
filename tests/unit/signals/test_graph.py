"""Unit tests for NetworkX graph engine — pure functions, no DB."""
import networkx as nx

from flow_intel.signals.graph import compute_network_alpha_score, find_interlock_clusters


def test_compute_network_alpha_no_signals():
    """No signals → signal component is 0; interlock + pressure still contribute."""
    score = compute_network_alpha_score([], 3, "NONE")
    assert 0 < score < 50


def test_compute_network_alpha_net_sell_penalty():
    """NET_SELL pressure → lower score than NET_BUY for same cluster_score."""
    score_buy = compute_network_alpha_score([{"cluster_score": 85}], 3, "NET_BUY")
    score_sell = compute_network_alpha_score([{"cluster_score": 85}], 3, "NET_SELL")
    assert score_buy > score_sell


def test_compute_network_alpha_saturates():
    """Max signal + max interlock + NET_BUY → exactly 100.0."""
    score = compute_network_alpha_score([{"cluster_score": 100}], 10, "NET_BUY")
    assert score == 100.0


def test_find_interlock_clusters_excludes_isolated():
    """Isolated nodes must not appear in any returned cluster."""
    G = nx.Graph()
    G.add_edge("KAPLM", "RALYH", weight=1)
    G.add_node("ALONE")
    clusters = find_interlock_clusters(G)
    flat = [t for c in clusters for t in c]
    assert "ALONE" not in flat
    assert "KAPLM" in flat


def test_find_interlock_clusters_min_companies():
    """Clusters smaller than min_companies are excluded."""
    G = nx.Graph()
    G.add_edge("A", "B", weight=1)
    assert find_interlock_clusters(G, min_companies=3) == []
