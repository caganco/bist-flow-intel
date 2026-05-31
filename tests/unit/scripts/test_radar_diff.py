"""Unit tests for radar_diff state comparison logic — no DB, no network."""
import json
import sys
from pathlib import Path

import pytest

# Make scripts/ importable
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from radar_diff import (  # noqa: E402
    SCORE_CHANGE_THRESHOLD,
    _cluster_key,
    _dedupe_clusters,
    _diff,
    _load_state,
    _save_state,
)


def test_radar_diff_detects_new_cluster():
    """New cluster absent from previous state → ticker in changed list."""
    current = {
        "KAPLM|2025-01-01": {
            "ticker": "KAPLM", "score": "12.5000", "insider_count": 3
        }
    }
    changed = _diff(current, {})
    assert "KAPLM" in changed


def test_radar_diff_skips_unchanged():
    """Same cluster, same score, same insider_count → empty changed list."""
    key = "KAPLM|2025-01-01"
    current = {key: {"ticker": "KAPLM", "score": "12.5000", "insider_count": 3}}
    previous = {"clusters": {key: {"score": "12.5000", "insider_count": 3}}}
    assert _diff(current, previous) == []


def test_radar_diff_detects_score_change_above_threshold():
    """Score change >= SCORE_CHANGE_THRESHOLD → ticker reported."""
    key = "KAPLM|2025-01-01"
    current = {key: {"ticker": "KAPLM", "score": "20.0000", "insider_count": 3}}
    previous = {"clusters": {key: {"score": "12.0000", "insider_count": 3}}}
    assert abs(20.0 - 12.0) >= SCORE_CHANGE_THRESHOLD
    assert "KAPLM" in _diff(current, previous)


def test_radar_diff_skips_small_score_change():
    """Score change < threshold → not reported."""
    key = "KAPLM|2025-01-01"
    current = {key: {"ticker": "KAPLM", "score": "14.0000", "insider_count": 3}}
    previous = {"clusters": {key: {"score": "12.0000", "insider_count": 3}}}
    assert abs(14.0 - 12.0) < SCORE_CHANGE_THRESHOLD
    assert _diff(current, previous) == []


def test_radar_diff_detects_new_insider():
    """Insider count increased → ticker reported."""
    key = "KAPLM|2025-01-01"
    current = {key: {"ticker": "KAPLM", "score": "12.5000", "insider_count": 4}}
    previous = {"clusters": {key: {"score": "12.5000", "insider_count": 3}}}
    assert "KAPLM" in _diff(current, previous)


def test_radar_diff_multiple_tickers_only_changed_returned():
    """Only changed tickers appear; unchanged tickers are filtered out."""
    current = {
        "KAPLM|2025-01-01": {"ticker": "KAPLM", "score": "12.5000", "insider_count": 3},
        "RALYH|2025-01-01": {"ticker": "RALYH", "score": "30.0000", "insider_count": 5},
    }
    previous = {
        "clusters": {
            "KAPLM|2025-01-01": {"score": "12.5000", "insider_count": 3},
            # RALYH was 8.0, now 30.0 → delta = 22 >= 5
            "RALYH|2025-01-01": {"score": "8.0000", "insider_count": 5},
        }
    }
    changed = _diff(current, previous)
    assert "KAPLM" not in changed
    assert "RALYH" in changed


def test_radar_diff_save_load_roundtrip(tmp_path):
    """State saved to file and loaded back preserves all cluster data."""
    current = {
        "KAPLM|2025-01-01": {"ticker": "KAPLM", "score": "12.5000", "insider_count": 3},
        "RALYH|2025-04-01": {"ticker": "RALYH", "score": "8.0000", "insider_count": 2},
    }
    state_path = tmp_path / ".radar_state.json"
    _save_state(state_path, current)
    loaded = _load_state(state_path)
    assert "KAPLM|2025-01-01" in loaded["clusters"]
    assert loaded["clusters"]["KAPLM|2025-01-01"]["score"] == "12.5000"
    assert loaded["clusters"]["RALYH|2025-04-01"]["insider_count"] == 2


def test_radar_diff_load_missing_state(tmp_path):
    """Missing state file returns empty dict without error."""
    result = _load_state(tmp_path / "nonexistent.json")
    assert result == {}


def test_cluster_key_format():
    """Cluster key format is stable ticker|window_start|window_end."""
    key = _cluster_key("KAPLM", "2025-01-01", "2025-03-31")
    assert key == "KAPLM|2025-01-01|2025-03-31"


def test_dedupe_collapses_overlapping_windows():
    """Same ticker+window_start, different window_end → single entry, max score."""
    clusters = [
        {"ticker": "MACKO", "window_start": "2025-12-23", "window_end": "2025-12-29",
         "score": "72.5", "insider_count": 4},
        {"ticker": "MACKO", "window_start": "2025-12-23", "window_end": "2025-12-23",
         "score": "47.5", "insider_count": 2},
    ]
    result = _dedupe_clusters(clusters)
    assert len(result) == 1
    assert float(result["MACKO|2025-12-23"]["score"]) == 72.5


def test_dedupe_keeps_distinct_window_starts():
    """Different window_start → separate entries kept."""
    clusters = [
        {"ticker": "SARKY", "window_start": "2025-05-27", "window_end": "2025-05-27",
         "score": "47.5", "insider_count": 2},
        {"ticker": "SARKY", "window_start": "2026-05-21", "window_end": "2026-05-21",
         "score": "47.5", "insider_count": 2},
    ]
    assert len(_dedupe_clusters(clusters)) == 2
