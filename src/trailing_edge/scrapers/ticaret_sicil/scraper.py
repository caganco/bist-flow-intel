"""Orchestrator: TSG search → PDF → OCR → parse → fuzzy match → DB.

NOTE on BFS: Turkish registries have no person→company reverse lookup (recon,
TASK-007 S2), so automatic graph expansion from discovered names is impossible
on this source. `run_seed` therefore scrapes exactly the company names it is
given. Expansion happens by feeding new seed names in, not by traversal.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from trailing_edge.core.db import get_session
from trailing_edge.core.logging import get_logger
from trailing_edge.models.graph import Person
from trailing_edge.models.unlisted import PersonUnlistedRole, UnlistedCompany
from trailing_edge.scrapers.kap.helpers import normalize_name
from trailing_edge.scrapers.ticaret_sicil.client import TsgClient
from trailing_edge.scrapers.ticaret_sicil.matcher import match_person_name
from trailing_edge.scrapers.ticaret_sicil.ocr import pdf_to_text
from trailing_edge.scrapers.ticaret_sicil.parser import IlanRow, parse_gazette_ocr

_log = get_logger(__name__)

_MGMT_KEYWORDS = ("YÖNET", "TEMS", "KURUL", "MÜDÜR")
_PDF_VIEW_URL = "/view/hizlierisim/pdf_goster.php?Guid="


def _infer_tsg_role_type(role: str | None) -> str:
    """Map a TSG notice role to a role_type. Distinct from KAP's mapper because
    TSG language differs ("Temsile Yetkili" = authorized signatory = EXEC)."""
    if not role:
        return "FOUNDER"
    r = role.casefold()
    if "yönetim kurulu" in r or "yk " in r:
        return "BOARD"
    if "denet" in r:
        return "AUDITOR"
    if "temsil" in r or "müdür" in r or "imza" in r:
        return "EXEC"
    if "ortak" in r or "kurucu" in r or "pay sahibi" in r:
        return "FOUNDER"
    return "FOUNDER"


@dataclass
class TsgScrapeResult:
    companies_inserted: int = 0
    roles_inserted: int = 0
    persons_matched: int = 0       # person_id NOT NULL
    persons_unmatched: int = 0     # person_id IS NULL


async def load_kap_persons() -> list[tuple[int, str]]:
    """[(id, name_normalized)] for fuzzy matching against KAP persons."""
    async with get_session() as session:
        result = await session.execute(select(Person.id, Person.name_normalized))
        return [(row[0], row[1]) for row in result.all()]


def _pick_notice(rows: list[IlanRow]) -> IlanRow | None:
    """Prefer the most recent management/representation notice (has people);
    fall back to the most recent notice of any kind."""
    if not rows:
        return None
    mgmt = [
        r for r in rows
        if r.ilan_type and any(k in r.ilan_type.upper() for k in _MGMT_KEYWORDS)
    ]
    pool = mgmt or rows
    return max(pool, key=lambda r: r.gazette_date or date.min)


async def _upsert_company(session, record, notice: IlanRow, base_url: str) -> int:
    """Insert/find the unlisted company; return its id. Dedup on sicil_no when
    present, else on name_normalized."""
    name_norm = normalize_name(record.company_name)
    source_url = f"{base_url}{_PDF_VIEW_URL}{notice.pdf_guid}"

    if notice.sicil_no:
        existing = await session.execute(
            select(UnlistedCompany.id).where(UnlistedCompany.sicil_no == notice.sicil_no)
        )
    else:
        existing = await session.execute(
            select(UnlistedCompany.id).where(UnlistedCompany.name_normalized == name_norm)
        )
    found = existing.scalar_one_or_none()
    if found is not None:
        return found

    result = await session.execute(
        pg_insert(UnlistedCompany)
        .values(
            name=record.company_name,
            name_normalized=name_norm,
            sicil_no=notice.sicil_no,
            city=notice.city,
            gazette_issue=notice.gazette_issue,
            founded_date=record.founded_date,
            source_url=source_url,
            raw_text=record.raw_text,
        )
        .returning(UnlistedCompany.id)
    )
    return result.scalar_one()


async def _upsert_role(
    session, company_id: int, person, kap_persons: list[tuple[int, str]]
) -> tuple[bool, bool]:
    """Fuzzy-match person to KAP and upsert the role.
    Returns (inserted, matched)."""
    person_id, confidence, method = match_person_name(person.name, kap_persons)
    role_type = _infer_tsg_role_type(person.role)

    stmt = (
        pg_insert(PersonUnlistedRole)
        .values(
            person_id=person_id,
            raw_person_name=person.name,
            unlisted_company_id=company_id,
            role=person.role,
            role_type=role_type,
            match_confidence=round(confidence, 3) if person_id else None,
            match_method=method,
        )
        .on_conflict_do_nothing(constraint="uq_person_unlisted_role")
    )
    result = await session.execute(stmt)
    inserted = result.rowcount == 1
    return inserted, person_id is not None


async def scrape_company(
    company_name: str,
    client: TsgClient,
    kap_persons: list[tuple[int, str]],
    result: TsgScrapeResult,
) -> None:
    """Search, fetch the best notice PDF, OCR, isolate the target block, and
    persist company + roles."""
    rows = await client.search_company(company_name)
    notice = _pick_notice(rows)
    if notice is None:
        _log.warning("tsg_no_notice", company=company_name)
        return

    pdf_bytes = await client.fetch_pdf_bytes(notice.pdf_guid)
    if not pdf_bytes:
        _log.warning("tsg_no_pdf", company=company_name, guid=notice.pdf_guid)
        return

    ocr_text = pdf_to_text(pdf_bytes)
    record = parse_gazette_ocr(ocr_text, company_name)
    if record is None:
        _log.warning("tsg_no_block_match", company=company_name)
        return

    cfg_base = client._base_url
    async with get_session() as session:
        company_id = await _upsert_company(session, record, notice, cfg_base)
        result.companies_inserted += 1

        for person in record.persons:
            inserted, matched = await _upsert_role(
                session, company_id, person, kap_persons
            )
            if inserted:
                result.roles_inserted += 1
                if matched:
                    result.persons_matched += 1
                else:
                    result.persons_unmatched += 1

    _log.info(
        "tsg_company_done",
        company=record.company_name,
        persons=len(record.persons),
    )


async def run_seed(seed_companies: list[str]) -> TsgScrapeResult:
    """Scrape each seed company name. One headful login covers the whole batch;
    the human solves a CAPTCHA per search and per PDF view."""
    result = TsgScrapeResult()
    kap_persons = await load_kap_persons()
    _log.info("tsg_seed_start", seeds=len(seed_companies), kap_persons=len(kap_persons))

    async with TsgClient() as client:
        await client.login()
        for name in seed_companies:
            try:
                await scrape_company(name, client, kap_persons, result)
            except Exception as e:
                _log.error("tsg_company_failed", company=name, error=str(e))

    return result
