"""Unit tests for sell-side event grouping (diagnostic-only, no DB)."""
from datetime import date
from decimal import Decimal

from trailing_edge.signals.sell_side import (
    SellSideEvent,
    SellTxRow,
    group_sell_side_events,
)


def _row(disc, ticker, d, name, value):
    return SellTxRow(
        disclosure_id=disc,
        ticker=ticker,
        transaction_date=date(2026, 1, d),
        insider_name=name,
        total_value_try=Decimal(str(value)) if value is not None else None,
    )


def test_empty_input():
    assert group_sell_side_events([]) == []


def test_one_event_per_disclosure():
    rows = [
        _row(1, "ABCD", 5, "INSIDER A", 1000),
        _row(1, "ABCD", 6, "INSIDER B", 2000),
        _row(2, "ABCD", 9, "INSIDER A", 500),
    ]
    events = group_sell_side_events(rows)
    assert len(events) == 2
    assert {e.disclosure_id for e in events} == {1, 2}


def test_window_and_insiders_and_value_aggregation():
    rows = [
        _row(7, "WXYZ", 10, "INSIDER A", 1000),
        _row(7, "WXYZ", 12, "INSIDER A", 1500),  # same insider, deduped
        _row(7, "WXYZ", 11, "INSIDER B", None),  # null value tolerated
    ]
    (event,) = group_sell_side_events(rows)
    assert isinstance(event, SellSideEvent)
    assert event.window_start == date(2026, 1, 10)
    assert event.window_end == date(2026, 1, 12)
    assert event.insiders == ("INSIDER A", "INSIDER B")
    assert event.insider_count == 2
    assert event.total_sell_value_try == Decimal("2500")


def test_all_null_values_gives_none_total():
    rows = [_row(3, "NULL", 1, "X", None), _row(3, "NULL", 2, "Y", None)]
    (event,) = group_sell_side_events(rows)
    assert event.total_sell_value_try is None


def test_deterministic_order():
    rows = [
        _row(2, "BBBB", 9, "X", 1),
        _row(1, "AAAA", 5, "Y", 1),
        _row(3, "AAAA", 3, "Z", 1),
    ]
    events = group_sell_side_events(rows)
    keys = [(e.ticker, e.window_end, e.disclosure_id) for e in events]
    assert keys == sorted(keys)
    assert events[0].ticker == "AAAA"  # AAAA sorts before BBBB
