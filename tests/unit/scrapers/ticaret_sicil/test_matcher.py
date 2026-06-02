"""Unit tests for Ticaret Sicil fuzzy person-name matcher."""

from flow_intel.scrapers.ticaret_sicil.matcher import (
    batch_match_persons,
    match_person_name,
    normalize_name_tr,
)

KAP_PERSONS = [
    (1, "riza kandemir"),
    (2, "enver gecgel"),
    (3, "feridun gecgel"),
    (4, "muhammed deniz"),
]


def test_exact_match():
    """Türkçe karakter normalizasyonuyla birebir eşleşme → EXACT, conf=1.0"""
    pid, conf, method = match_person_name("Rıza Kandemir", KAP_PERSONS)
    assert pid == 1
    assert conf == 1.0
    assert method == "EXACT"


def test_fuzzy_match_typo():
    """'Rıza Kandamir' (typo) → hâlâ person 1 eşleşmeli, conf ≥ 0.85"""
    pid, conf, method = match_person_name("Rıza Kandamir", KAP_PERSONS)
    assert pid == 1
    assert conf >= 0.85


def test_word_order_invariant():
    """'Kandemir Rıza' → token_sort_ratio sayesinde person 1 eşleşmeli"""
    pid, conf, method = match_person_name("Kandemir Rıza", KAP_PERSONS)
    assert pid == 1


def test_no_match_below_threshold():
    """Threshold altında kalan isimler → person_id=None, conf=0.0"""
    pid, conf, method = match_person_name("Ahmet Yılmaz", KAP_PERSONS, threshold=0.85)
    assert pid is None
    assert conf == 0.0
    assert method is None


def test_normalize_turkish_chars():
    assert normalize_name_tr("Rıza Kandemir") == "riza kandemir"
    assert normalize_name_tr("İbrahim Şahin") == "ibrahim sahin"
    assert normalize_name_tr("Ömer Çelik") == "omer celik"


def test_batch_match():
    results = batch_match_persons(["Rıza Kandemir", "Bilinmeyen Kişi"], KAP_PERSONS)
    assert results["Rıza Kandemir"][0] == 1
    assert results["Bilinmeyen Kişi"][0] is None
