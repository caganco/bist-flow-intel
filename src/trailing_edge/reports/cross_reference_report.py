"""Cross-reference brief (KAP ↔ TSG) - HTML + PDF export."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import jinja2
from sqlalchemy import select

from trailing_edge.core.db import get_session
from trailing_edge.core.logging import get_logger
from trailing_edge.models.graph import Person
from trailing_edge.reports.forensic_report import generate_pdf_report
from trailing_edge.signals.cross_reference import (
    CrossReferenceReport,
    build_cross_reference_report,
)

_log = get_logger(__name__)
_TEMPLATES_DIR = Path(__file__).parent / "templates"


def render_cross_reference_html(report: CrossReferenceReport) -> str:
    """Pure Jinja2 render - sync, no DB."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=True,
    )
    return env.get_template("cross_reference.html").render(report=report)


async def _resolve_person_id(person_name: str) -> int | None:
    from trailing_edge.scrapers.kap.helpers import normalize_name

    norm = normalize_name(person_name)
    async with get_session() as session:
        return (
            await session.execute(select(Person.id).where(Person.name_normalized == norm))
        ).scalar_one_or_none()


async def generate_cross_reference_report(
    top_n: int = 20,
    person: str | None = None,
    output_format: str = "pdf",
) -> Path:
    """Build the KAP↔TSG cross-reference report → HTML and/or PDF."""
    if person:
        pid = await _resolve_person_id(person)
        person_ids = [pid] if pid is not None else []
        report = await build_cross_reference_report(person_ids=person_ids)
    else:
        report = await build_cross_reference_report(top_n=top_n)

    html = render_cross_reference_html(report)
    today = date.today()

    reports_dir = Path("reports") / "cross-reference"
    reports_dir.mkdir(parents=True, exist_ok=True)
    html_path = reports_dir / f"{today}_cross_reference.html"
    pdf_path = reports_dir / f"{today}_cross_reference.pdf"

    if output_format in ("html", "both"):
        html_path.write_text(html, encoding="utf-8")
        _log.info("cross_reference_html_written", path=str(html_path))

    if output_format in ("pdf", "both"):
        await generate_pdf_report(html, pdf_path)
        _log.info("cross_reference_pdf_written", path=str(pdf_path))
        return pdf_path

    return html_path
