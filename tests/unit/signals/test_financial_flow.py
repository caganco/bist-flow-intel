"""Unit tests for financial_flow module - no DB, no network."""
from decimal import Decimal

import pytest

from trailing_edge.signals.financial_flow import (
    RelatedPartyFinding,
    TenderFinding,
    build_management_bridges,
)


def test_related_party_finding_none_match():
    """NONE match_method accepted; fields nullable."""
    f = RelatedPartyFinding(
        source_company="RALYH",
        counterparty=None,
        transaction_type=None,
        amount_try=None,
        period=None,
        disclosure_url="https://www.kap.org.tr/tr/sirket-bilgileri/ozet/RALYH",
        raw_excerpt="Tespit edilmedi.",
        match_method="NONE",
    )
    assert f.match_method == "NONE"
    assert f.counterparty is None
    assert f.amount_try is None


def test_related_party_finding_named_match():
    """NAMED match_method stores counterparty and amount."""
    f = RelatedPartyFinding(
        source_company="KAPLM",
        counterparty="HERA TEKNİK YAPI A.Ş.",
        transaction_type="hizmet",
        amount_try=Decimal("1500000"),
        period="2024 Q4",
        disclosure_url="https://www.kap.org.tr/tr/example",
        raw_excerpt="Hera Teknik Yapı A.Ş.'ye 1.500.000 TL hizmet bedeli ödenmiştir.",
        match_method="NAMED",
    )
    assert f.match_method == "NAMED"
    assert f.counterparty == "HERA TEKNİK YAPI A.Ş."
    assert f.amount_try == Decimal("1500000")


def test_related_party_finding_invalid_match_method():
    """Invalid match_method raises ValueError."""
    with pytest.raises(ValueError, match="match_method"):
        RelatedPartyFinding(
            source_company="RALYH",
            counterparty=None,
            transaction_type=None,
            amount_try=None,
            period=None,
            disclosure_url="https://example.com",
            raw_excerpt="",
            match_method="INVALID",
        )


def test_tender_finding_requires_source_url():
    """Empty source_url raises ValueError."""
    with pytest.raises(ValueError, match="source_url"):
        TenderFinding(
            company="HERA TEKNİK YAPI A.Ş.",
            tender_authority=None,
            tender_subject=None,
            amount_try=None,
            date=None,
            source_url="",
        )


def test_tender_finding_with_url():
    """Valid TenderFinding accepted when source_url provided."""
    t = TenderFinding(
        company="HERA TEKNİK YAPI A.Ş.",
        tender_authority="İller Bankası A.Ş.",
        tender_subject="Yapım işi",
        amount_try=Decimal("5000000"),
        date="2025-03-15",
        source_url="https://ekap.kik.gov.tr/example/12345",
    )
    assert t.company == "HERA TEKNİK YAPI A.Ş."
    assert t.source_url.startswith("https://")


def test_build_management_bridges_basic():
    """build_management_bridges derives bridges from existing footprint data."""
    from unittest.mock import MagicMock

    fp = MagicMock()
    fp.full_name = "RIZA KANDEMİR"
    fp.listed_companies = [{"ticker": "KAPLM", "company_name": "Kaplamin A.Ş."}]
    fp.unlisted_companies = [
        {"name": "HERA TEKNİK YAPI A.Ş."},
        {"name": "RAL ENERJİ A.Ş."},
    ]

    bridges = build_management_bridges([fp])
    assert len(bridges) == 2
    companies = {b["unlisted"] for b in bridges}
    assert "HERA TEKNİK YAPI A.Ş." in companies
    assert "RAL ENERJİ A.Ş." in companies
    assert all(b["person"] == "RIZA KANDEMİR" for b in bridges)
    assert all(b["listed"] == "Kaplamin A.Ş." for b in bridges)


def test_build_management_bridges_dedup():
    """Same (person, listed, unlisted) triple not duplicated across two footprints."""
    from unittest.mock import MagicMock

    fp1 = MagicMock()
    fp1.full_name = "TEST KİŞİ"
    fp1.listed_companies = [{"ticker": "AAA", "company_name": "A Şirketi A.Ş."}]
    fp1.unlisted_companies = [{"name": "UNLISTED X"}]

    fp2 = MagicMock()
    fp2.full_name = "TEST KİŞİ"
    fp2.listed_companies = [{"ticker": "AAA", "company_name": "A Şirketi A.Ş."}]
    fp2.unlisted_companies = [{"name": "UNLISTED X"}]

    bridges = build_management_bridges([fp1, fp2])
    assert len(bridges) == 1, "Duplicate triple must be deduplicated"


def test_build_management_bridges_empty():
    """Empty footprint list returns empty bridges."""
    assert build_management_bridges([]) == []


def test_financial_flow_template_no_forbidden_words():
    """Rendered financial_flow.html contains no forbidden language."""
    from pathlib import Path
    from unittest.mock import MagicMock

    import jinja2

    templates_dir = Path(__file__).parents[3] / "src" / "trailing_edge" / "reports" / "templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_dir)),
        autoescape=True,
    )

    data = MagicMock()
    data.related_party_findings = [
        RelatedPartyFinding(
            source_company="RALYH",
            counterparty=None,
            transaction_type=None,
            amount_try=None,
            period=None,
            disclosure_url="https://example.com",
            raw_excerpt="Tespit edilmedi.",
            match_method="NONE",
        )
    ]
    data.tender_findings = []
    data.management_bridges = []

    rendered = env.get_template("financial_flow.html").render(data=data)

    forbidden = ["gizli ortak", "asset transfer", "kartel", "usulsüz", "saptanmıştır", "şüpheli"]
    for word in forbidden:
        assert word not in rendered.lower(), f"Forbidden word found in template: {word!r}"


def test_financial_flow_template_negative_finding_renders_note():
    """NONE match_method finding renders the raw_excerpt note."""
    from pathlib import Path
    from unittest.mock import MagicMock

    import jinja2

    templates_dir = Path(__file__).parents[3] / "src" / "trailing_edge" / "reports" / "templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_dir)),
        autoescape=True,
    )

    data = MagicMock()
    data.related_party_findings = [
        RelatedPartyFinding(
            source_company="RALYH",
            counterparty=None,
            transaction_type=None,
            amount_try=None,
            period=None,
            disclosure_url="https://example.com",
            raw_excerpt="Bu sürümde çekilemedi.",
            match_method="NONE",
        )
    ]
    data.tender_findings = []
    data.management_bridges = []

    rendered = env.get_template("financial_flow.html").render(data=data)
    assert "tespit edilmedi" in rendered.lower()
    assert "Bu sürümde çekilemedi." in rendered
