"""Unit tests for seed_graph_from_insider_tx company name override logic."""
import importlib.util
import sys
from pathlib import Path

import pytest

# Load seed module (executes load_dotenv() harmlessly if .env absent)
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "src"))
_spec = importlib.util.spec_from_file_location(
    "seed_graph", _ROOT / "scripts" / "seed_graph_from_insider_tx.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_resolve = _mod._resolve_company_name
_GENERIC = _mod._GENERIC_COMPANY_TITLES


def test_yaml_override_takes_precedence_over_api_name():
    """YAML entry replaces any API-derived name, including real-looking ones."""
    known = {"KAPLM": "Kaplamin Ambalaj Sanayi ve Ticaret A.Ş."}
    name = _resolve("KAPLM", "SOME OTHER NAME FROM API", known)
    assert name == "Kaplamin Ambalaj Sanayi ve Ticaret A.Ş."


def test_generic_title_filtered_for_unknown_ticker():
    """Generic platform title is rejected for tickers not in YAML."""
    for generic in _GENERIC:
        assert _resolve("UNKWN", generic, {}) is None


def test_real_name_accepted_for_unknown_ticker():
    """Non-generic API name accepted for tickers not in YAML."""
    name = _resolve("UNKWN", "Örnek Anonim Şirketi A.Ş.", {})
    assert name == "Örnek Anonim Şirketi A.Ş."


def test_empty_api_name_returns_none():
    """None/empty raw_name with no YAML override → None (skip company)."""
    assert _resolve("UNKWN", None, {}) is None
    assert _resolve("UNKWN", "", {}) is None
    assert _resolve("UNKWN", "   ", {}) is None


def test_yaml_override_used_even_when_api_name_is_none():
    """YAML entry creates company even if API returned no name for that ticker."""
    known = {"RALYH": "Ral Yatırım Holding A.Ş."}
    name = _resolve("RALYH", None, known)
    assert name == "Ral Yatırım Holding A.Ş."


def test_generic_title_case_insensitive():
    """Generic name filter is case-insensitive."""
    for variant in ["kamuyu aydinlatma platformu", "KAMUYU AYDINLATMA PLATFORMU",
                    "Kamuyu Aydınlatma Platformu"]:
        result = _resolve("UNKWN", variant, {})
        # Only exact uppercase match is stored in _GENERIC, so lowercase passes through.
        # The filter normalises with .upper() — all variants should be rejected.
        assert result is None, f"Expected None for variant {variant!r}"
