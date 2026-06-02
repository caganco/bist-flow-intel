"""Unit tests for compute_cluster_score and _find_cluster_events."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from flow_intel.signals.cluster import _find_cluster_events, compute_cluster_score

_WEIGHTS = {"insider_count": 0.5, "role_seniority": 0.3, "recency": 0.2}
_WINDOW = 30


def test_compute_cluster_score_ceo_beats_board_member():
    score_ceo = compute_cluster_score(2, ["Genel Müdür"], 0, _WEIGHTS, _WINDOW)
    score_board = compute_cluster_score(2, ["Yönetim Kurulu Üyesi"], 0, _WEIGHTS, _WINDOW)
    assert score_ceo > score_board


def test_compute_cluster_score_recency_decay():
    score_fresh = compute_cluster_score(2, [], 0, _WEIGHTS, _WINDOW)
    score_stale = compute_cluster_score(2, [], 15, _WEIGHTS, _WINDOW)
    assert score_fresh > score_stale


def test_compute_cluster_score_recency_zero_at_window_limit():
    score = compute_cluster_score(2, [], _WINDOW, _WEIGHTS, _WINDOW)
    # recency_score=0, insider_count_score=0.25, role_seniority_score=0.5(default)
    expected = Decimal(str((0.25 * 0.5 + 0.5 * 0.3 + 0.0 * 0.2) * 100)).quantize(Decimal("0.0001"))
    assert score == expected


def test_compute_cluster_score_saturates_at_five_insiders():
    s5 = compute_cluster_score(5, [], 0, _WEIGHTS, _WINDOW)
    s10 = compute_cluster_score(10, [], 0, _WEIGHTS, _WINDOW)
    assert s5 == s10


def test_compute_cluster_score_all_roles_none_uses_default():
    score_none = compute_cluster_score(2, [None, None], 0, _WEIGHTS, _WINDOW)
    score_explicit_default = compute_cluster_score(2, ["unknown_role"], 0, _WEIGHTS, _WINDOW)
    assert score_none == score_explicit_default


def _make_tx(insider: str, tx_date: date, role: str | None = None):
    return SimpleNamespace(insider_name=insider, transaction_date=tx_date, insider_role=role)


def test_single_insider_produces_no_cluster():
    txs = [_make_tx("Ali", date(2026, 1, 10))]
    events = _find_cluster_events(txs, _WINDOW, min_count=2, as_of_date=None)
    assert events == []


def test_two_insiders_within_window_produces_cluster():
    txs = [
        _make_tx("Ali", date(2026, 1, 10)),
        _make_tx("Veli", date(2026, 1, 20)),
    ]
    events = _find_cluster_events(txs, _WINDOW, min_count=2, as_of_date=None)
    assert len(events) == 1
    ws, we, distinct, _ = events[0]
    assert ws == date(2026, 1, 10)
    assert we == date(2026, 1, 20)
    assert distinct == {"Ali", "Veli"}


def test_same_insider_twice_counts_as_one():
    txs = [
        _make_tx("Ali", date(2026, 1, 10)),
        _make_tx("Ali", date(2026, 1, 20)),
    ]
    events = _find_cluster_events(txs, _WINDOW, min_count=2, as_of_date=None)
    assert events == []


def test_two_insiders_outside_window_no_cluster():
    txs = [
        _make_tx("Ali", date(2026, 1, 1)),
        _make_tx("Veli", date(2026, 2, 5)),  # 35 days later > window_days=30
    ]
    events = _find_cluster_events(txs, _WINDOW, min_count=2, as_of_date=None)
    assert events == []


def test_as_of_date_filters_future_transactions():
    txs = [
        _make_tx("Ali", date(2026, 1, 10)),
        _make_tx("Veli", date(2026, 1, 20)),
        _make_tx("Hasan", date(2026, 1, 25)),
    ]
    # as_of_date before Hasan's buy
    events = _find_cluster_events(txs, _WINDOW, min_count=2, as_of_date=date(2026, 1, 22))
    # Expect cluster at (Jan10, Jan20) but not Jan25
    assert all(we <= date(2026, 1, 22) for _, we, _, _ in events)


def test_cluster_strengthens_when_new_insider_joins():
    txs = [
        _make_tx("Ali", date(2026, 1, 10)),
        _make_tx("Veli", date(2026, 1, 20)),
        _make_tx("Hasan", date(2026, 1, 25)),  # 3rd insider
    ]
    events = _find_cluster_events(txs, _WINDOW, min_count=2, as_of_date=None)
    # Two distinct (window_start, window_end) pairs: (Jan10,Jan20) and (Jan10,Jan25)
    window_ends = {we for _, we, _, _ in events}
    assert date(2026, 1, 20) in window_ends
    assert date(2026, 1, 25) in window_ends
