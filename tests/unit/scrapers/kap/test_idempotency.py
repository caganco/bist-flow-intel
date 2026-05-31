"""Unit tests for natural_key_hash idempotency and sensitivity."""
from datetime import date
from decimal import Decimal

from flow_intel.scrapers.kap.types import compute_natural_key_hash


def test_natural_key_hash_deterministic():
    h1 = compute_natural_key_hash(
        "SERVET NASIR", date(2026, 5, 25), "SELL", Decimal("2500000"), Decimal("18.45")
    )
    h2 = compute_natural_key_hash(
        "SERVET NASIR", date(2026, 5, 25), "SELL", Decimal("2500000"), Decimal("18.45")
    )
    assert h1 == h2


def test_natural_key_hash_price_sensitivity():
    h1 = compute_natural_key_hash("X", date(2026, 1, 1), "BUY", Decimal("100"), Decimal("10.00"))
    h2 = compute_natural_key_hash("X", date(2026, 1, 1), "BUY", Decimal("100"), Decimal("10.01"))
    assert h1 != h2


def test_natural_key_hash_none_price():
    h = compute_natural_key_hash("X", date(2026, 1, 1), "BUY", Decimal("100"), None)
    assert len(h) == 64
    assert h.isalnum()


def test_natural_key_hash_different_dates():
    h1 = compute_natural_key_hash("X", date(2026, 1, 1), "BUY", Decimal("100"), None)
    h2 = compute_natural_key_hash("X", date(2026, 1, 2), "BUY", Decimal("100"), None)
    assert h1 != h2


def test_natural_key_hash_different_type():
    h1 = compute_natural_key_hash("X", date(2026, 1, 1), "BUY", Decimal("100"), None)
    h2 = compute_natural_key_hash("X", date(2026, 1, 1), "SELL", Decimal("100"), None)
    assert h1 != h2


def test_natural_key_hash_different_count():
    h1 = compute_natural_key_hash("X", date(2026, 1, 1), "BUY", Decimal("100"), None)
    h2 = compute_natural_key_hash("X", date(2026, 1, 1), "BUY", Decimal("101"), None)
    assert h1 != h2
