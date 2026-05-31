"""Fuzzy person-name matcher for Ticaret Sicil ↔ KAP persons cross-reference."""
from __future__ import annotations

from rapidfuzz import fuzz, process

from flow_intel.scrapers.kap.helpers import normalize_name

TR_CHAR_MAP = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def normalize_name_tr(name: str) -> str:
    """Türkçe ASCII transliteration + normalize_name().

    ONLY for matching — DB always stores the original name.
    TR map applied BEFORE casefold: "İ".casefold() = "i̇" (combining dot),
    which str.translate cannot handle. Mapping first avoids this.

    "Rıza Kandemir" → "riza kandemir"
    "İbrahim Şahin" → "ibrahim sahin"
    """
    return normalize_name(name.translate(TR_CHAR_MAP))


def match_person_name(
    raw_name: str,
    kap_persons: list[tuple[int, str]],
    threshold: float = 0.800,
) -> tuple[int | None, float, str | None]:
    """Match a raw TSG name against KAP persons using fuzzy matching.

    raw_name    — ham isim (TSG'den gelir, normalize edilir)
    kap_persons — [(person_id, name_normalized)] from persons table
    threshold   — minimum confidence (0.0–1.0); default 0.80

    Returns (person_id | None, confidence, method | None).

    method values: "EXACT" | "HIGH" (≥0.90) | "MEDIUM" (≥0.80) | "LOW" (≥0.70)
    Uses token_sort_ratio so "Kandemir Rıza" == "Rıza Kandemir" at score 100.
    """
    if not kap_persons:
        return None, 0.0, None

    query = normalize_name_tr(raw_name)
    # Apply same TR normalization to DB names (they may contain ı, ğ etc.)
    ids = [i for i, _ in kap_persons]
    names = [normalize_name_tr(n) for _, n in kap_persons]

    if query in names:
        return ids[names.index(query)], 1.0, "EXACT"

    result = process.extractOne(
        query,
        names,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=threshold * 100,
    )
    if result is None:
        return None, 0.0, None

    _best_name, score, best_idx = result
    confidence = round(score / 100, 3)
    method = "HIGH" if score >= 90 else ("MEDIUM" if score >= 80 else "LOW")
    return ids[best_idx], confidence, method


def batch_match_persons(
    raw_names: list[str],
    kap_persons: list[tuple[int, str]],
    threshold: float = 0.800,
) -> dict[str, tuple[int | None, float, str | None]]:
    """Batch version of match_person_name.

    Returns {raw_name: (person_id, confidence, method)} for all names.
    """
    return {name: match_person_name(name, kap_persons, threshold) for name in raw_names}
