"""Unit tests for BaseRateStats dataclass logic (pure computation, no DB)."""
from decimal import Decimal

import pytest

from flow_intel.signals.base_rate import BaseRateStats, _ZERO


def _stats(floats: list[float]) -> dict:
    """Helper: compute expected stats from a list of return values."""
    import statistics
    hits = sum(1 for v in floats if v > 0)
    return {
        "hit_rate_pct": round(hits / len(floats) * 100, 2),
        "median": round(statistics.median(floats), 2),
        "avg": round(sum(floats) / len(floats), 2),
    }


def test_hit_rate_calculation():
    expected = _stats([5.0, -3.0, 8.0, 1.0])
    assert expected["hit_rate_pct"] == 75.0


def test_hit_rate_all_positive():
    expected = _stats([1.0, 2.0, 3.0])
    assert expected["hit_rate_pct"] == 100.0


def test_hit_rate_all_negative():
    expected = _stats([-1.0, -2.0])
    assert expected["hit_rate_pct"] == 0.0


def test_base_rate_stats_zero_fields():
    stats = BaseRateStats(
        horizon_days=20,
        total_signals=0,
        signals_with_outcome=0,
        hit_rate_pct=_ZERO,
        median_return_pct=_ZERO,
        avg_return_pct=_ZERO,
        best_return_pct=_ZERO,
        worst_return_pct=_ZERO,
    )
    assert stats.hit_rate_pct == Decimal("0.00")
    assert stats.signals_with_outcome == 0
