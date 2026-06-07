"""Unit tests for the forensic TSG layer template - pure render, no DB."""
import base64
from datetime import date

from flow_intel.reports.forensic_report import ForensicReportData, generate_html_report
from flow_intel.signals.graph import NetworkCluster


def _base_data(**overrides) -> ForensicReportData:
    cluster = NetworkCluster(
        companies=["KAPLM"],
        shared_persons=[],
        total_interlock_weight=0,
        active_signals=[],
        net_pressure="NONE",
        network_alpha_score=0.0,
        as_of_date=date(2026, 5, 29),
    )
    kwargs = dict(
        ticker="KAPLM",
        company_name="Test A.Ş.",
        report_date=date(2026, 5, 29),
        network_cluster=cluster,
        transactions=[],
        board_connections=[],
        graph_png_b64=base64.b64encode(b"FAKE").decode(),
    )
    kwargs.update(overrides)
    return ForensicReportData(**kwargs)


def test_tsg_layer_renders_without_data():
    """Empty footprints → section header present, fallback row, no crash."""
    html = generate_html_report(_base_data())
    assert "Fiziki Dünya Bağlantıları" in html
    assert "mevcut değil" in html


def test_unknown_associates_section_renders():
    """Unknown associates present → ⚠ section + names rendered."""
    html = generate_html_report(
        _base_data(
            actor_footprints=[],
            unknown_associates=[
                {"raw_person_name": "MEHMET YILMAZ", "company_name": "Trio Teknik Yapı A.Ş.",
                 "role": "ORTAK"},
            ],
        )
    )
    assert "Bilinmeyen Ağ Üyeleri" in html
    assert "MEHMET YILMAZ" in html
