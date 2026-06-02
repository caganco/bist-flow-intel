"""Unit tests for graph seed helper functions (pure, no DB)."""

from flow_intel.scrapers.kap.helpers import infer_is_independent, infer_role_type, normalize_name


def test_normalize_strips_and_casefolds():
    assert normalize_name("  AHMET YILMAZ  ") == "ahmet yilmaz"


def test_normalize_collapses_whitespace():
    assert normalize_name("Mehmet  Kaya") == "mehmet kaya"


def test_normalize_already_clean():
    assert normalize_name("ali veli") == "ali veli"


def test_infer_role_type_board():
    assert infer_role_type("Yönetim Kurulu Üyesi") == "BOARD"


def test_infer_role_type_board_chairman():
    assert infer_role_type("Yönetim Kurulu Başkanı") == "BOARD"


def test_infer_role_type_exec_ceo():
    assert infer_role_type("Genel Müdür") == "EXEC"


def test_infer_role_type_auditor():
    assert infer_role_type("Denetim Kurulu Üyesi") == "AUDITOR"


def test_infer_role_type_default_none():
    assert infer_role_type(None) == "SHAREHOLDER"


def test_infer_role_type_default_unknown():
    assert infer_role_type("Bilinmeyen Görev") == "SHAREHOLDER"


def test_infer_is_independent_true():
    assert infer_is_independent("Bağımsız Yönetim Kurulu Üyesi") is True


def test_infer_is_independent_false():
    assert infer_is_independent("Yönetim Kurulu Üyesi") is False


def test_infer_is_independent_none():
    assert infer_is_independent(None) is False
