"""Unit tests for validate_actor_seeds — no DB."""
import flow_intel.scrapers.ticaret_sicil.targets as t
from flow_intel.scrapers.ticaret_sicil.targets import validate_actor_seeds


def test_validate_skips_empty_seeds(monkeypatch):
    """Empty-seed actors are dropped from the validated dict."""
    monkeypatch.setattr(t, "load_actor_seeds",
                        lambda: {"DOLU": ["Hera Teknik"], "BOS": []})
    valid = t.validate_actor_seeds()
    assert "DOLU" in valid
    assert "BOS" not in valid


def test_validate_skips_short_names(monkeypatch):
    """Company names shorter than 5 chars are filtered out; longer ones kept."""
    monkeypatch.setattr(t, "load_actor_seeds",
                        lambda: {"X": ["AB", "Hera Teknik"]})
    valid = t.validate_actor_seeds()
    assert valid["X"] == ["Hera Teknik"]


def test_validate_returns_valid_pairs():
    """Real yaml: Kandemir present, all seeds >= 5 chars."""
    valid = validate_actor_seeds()
    assert "RIZA KANDEMİR" in valid
    assert all(len(c) >= 5 for c in valid["RIZA KANDEMİR"])
