"""Unit tests for look-ahead-safe entry timing.

These prove the entry-date logic WITHOUT a database: entry is keyed to the
latest public disclosure (``published_at``, correction-aware) and is strictly
after it (t+1), so no information that was private on the transaction date is
used at entry.
"""
from datetime import date, datetime, timezone

import pytest

from trailing_edge.core.time import TR_TZ
from trailing_edge.signals.entry_timing import (
    ENTRY_OFFSET_TRADING_DAYS,
    entry_exit_offsets,
    look_ahead_safe_signal_date,
)


def _tr(year: int, month: int, day: int, hour: int = 10) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=TR_TZ)


def test_signal_date_picks_latest_disclosure():
    stamps = [_tr(2025, 10, 30), _tr(2025, 11, 3), _tr(2025, 10, 31)]
    assert look_ahead_safe_signal_date(stamps) == date(2025, 11, 3)


def test_correction_later_than_original_wins():
    # A correction filed after the original: its later published_at is the
    # look-ahead-safe instant (the corrected info was not public before it).
    original = _tr(2025, 10, 31, 9)
    correction = _tr(2025, 11, 5, 14)
    assert look_ahead_safe_signal_date([original, correction]) == date(2025, 11, 5)


def test_single_disclosure():
    assert look_ahead_safe_signal_date([_tr(2026, 2, 23)]) == date(2026, 2, 23)


def test_none_values_ignored():
    assert look_ahead_safe_signal_date([None, _tr(2026, 1, 5), None]) == date(2026, 1, 5)


def test_empty_raises():
    with pytest.raises(ValueError):
        look_ahead_safe_signal_date([])
    with pytest.raises(ValueError):
        look_ahead_safe_signal_date([None])


def test_utc_timestamp_converted_to_istanbul_date():
    # 2026-01-05 22:30 UTC == 2026-01-06 01:30 Istanbul (UTC+3) -> next calendar day.
    ts = datetime(2026, 1, 5, 22, 30, 0, tzinfo=timezone.utc)
    assert look_ahead_safe_signal_date([ts]) == date(2026, 1, 6)


def test_entry_is_t_plus_1_not_disclosure_day():
    assert ENTRY_OFFSET_TRADING_DAYS == 1
    entry, exit_ = entry_exit_offsets(20)
    assert entry == 1  # t+1, never 0 (the disclosure/transaction day itself)
    assert exit_ == 21  # horizon trading days after entry


@pytest.mark.parametrize("horizon", [5, 10, 21, 42, 63])
def test_entry_exit_offsets_horizons(horizon):
    entry, exit_ = entry_exit_offsets(horizon)
    assert entry == 1
    assert exit_ == 1 + horizon


def test_entry_exit_offsets_rejects_non_positive_horizon():
    with pytest.raises(ValueError):
        entry_exit_offsets(0)
    with pytest.raises(ValueError):
        entry_exit_offsets(-3)


def test_late_filing_entry_is_after_public_date_not_transaction_date():
    """The core look-ahead invariant.

    A cluster's last BUY transaction is 2025-10-31 (private until filed). The KAP
    filing becomes public 2025-11-05. Entry must be measured from the PUBLIC date
    and strictly after it (t+1) — never from the 2025-10-31 transaction date.
    """
    window_end = date(2025, 10, 31)
    signal_date = look_ahead_safe_signal_date([_tr(2025, 11, 5)])
    assert signal_date == date(2025, 11, 5)
    # The disclosure cannot predate the transactions it reports.
    assert signal_date >= window_end
    # Entry is strictly after the public date, so nothing private on
    # 2025-10-31..2025-11-05 is used at entry.
    entry_offset, _ = entry_exit_offsets(5)
    assert entry_offset >= 1
