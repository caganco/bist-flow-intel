"""KAP Yönetim Kurulu (management board) scraper.

Two-step per company:
  1. GET /tr/api/member/filter/{ticker}  → permaLink (JSON)
  2. GET /tr/sirket-bilgileri/genel/{permaLink}  → HTML → parse board table

Writes source='KAP_YONETIM' to person_company_roles.
"""
from __future__ import annotations

from datetime import datetime

from bs4 import BeautifulSoup

from flow_intel.core.http import RateLimitedClient
from flow_intel.core.logging import get_logger
from flow_intel.scrapers.kap.helpers import infer_role_type
from flow_intel.scrapers.kap.types import BoardMemberDTO

_log = get_logger(__name__)
_BASE = "https://www.kap.org.tr"


async def _get_permalink(http: RateLimitedClient, ticker: str) -> str | None:
    """GET /tr/api/member/filter/{ticker} → permaLink or None on failure.

    The API returns a JSON array; take the first element.
    """
    try:
        resp = await http.get(f"{_BASE}/tr/api/member/filter/{ticker}")
        data = resp.json()
        if isinstance(data, list):
            data = data[0] if data else {}
        return data.get("permaLink") or None
    except Exception as exc:
        _log.warning("permalink_fetch_failed", ticker=ticker, error=str(exc))
        return None


def parse_board_html(html: str) -> list[BoardMemberDTO]:
    """Parse management board members from the /tr/sirket-bilgileri/genel/{permaLink} page.

    The board table has 17 columns. It is identified by having a header that contains
    'Bağımsız Yönetim Kurulu Üyesi Olup Olmadığı' (independence flag column), which
    distinguishes it from the executive committee table (5 cols, no independence col).
    """
    soup = BeautifulSoup(html, "html.parser")

    board_table = None
    for table in soup.find_all("table"):
        thead = table.find("thead")
        if not thead:
            continue
        headers = [th.get_text(strip=True) for th in thead.find_all("th")]
        if any("Bağımsız Yönetim Kurulu Üyesi Olup" in h for h in headers):
            board_table = table
            break

    if board_table is None:
        return []

    thead = board_table.find("thead")
    if thead is None:
        return []
    headers = [th.get_text(strip=True) for th in thead.find_all("th")]

    # Resolve column indices from headers (robust against future column additions)
    def _col(fragment: str, fallback: int) -> int:
        return next((i for i, h in enumerate(headers) if fragment in h), fallback)

    col_name = _col("Soyad", 0)
    col_role = _col("Görevi", 3)
    col_date = _col("Seçilme Tarihi", 5)
    col_independent = _col("Bağımsız Yönetim Kurulu Üyesi Olup", 12)

    tbody = board_table.find("tbody")
    if not tbody:
        return []

    members: list[BoardMemberDTO] = []
    for row in tbody.find_all("tr"):
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if not cells:
            continue

        full_name = cells[col_name] if len(cells) > col_name else ""
        if not full_name:
            continue

        role = cells[col_role] if len(cells) > col_role else None
        date_str = cells[col_date] if len(cells) > col_date else ""
        independent_str = cells[col_independent] if len(cells) > col_independent else ""

        valid_from = None
        if date_str:
            try:
                valid_from = datetime.strptime(date_str, "%d/%m/%Y").date()
            except ValueError:
                pass

        # Use the dedicated independence column (more reliable than inferring from role text)
        is_independent = bool(
            independent_str
            and "Bağımsız" in independent_str
            and "Değil" not in independent_str
        )

        members.append(BoardMemberDTO(
            full_name=full_name,
            role=role,
            role_type=infer_role_type(role),
            is_independent=is_independent,
            valid_from=valid_from,
        ))

    return members


async def fetch_board(http: RateLimitedClient, ticker: str) -> list[BoardMemberDTO]:
    """Fetch and parse management board for a single ticker."""
    permalink = await _get_permalink(http, ticker)
    if not permalink:
        return []
    try:
        resp = await http.get(f"{_BASE}/tr/sirket-bilgileri/genel/{permalink}")
        members = parse_board_html(resp.text)
        _log.info("board_fetched", ticker=ticker, members=len(members))
        return members
    except Exception as exc:
        _log.warning("board_fetch_failed", ticker=ticker, error=str(exc))
        return []


async def scrape_all_companies(
    tickers: list[str] | None = None,
) -> dict[str, int]:
    """Scrape management board for all companies (or a subset).

    Returns {ticker: member_count_inserted}.
    Per-company failures log a warning and continue - no crash.
    Calls REFRESH MATERIALIZED VIEW CONCURRENTLY after all inserts.
    """
    from sqlalchemy import select, text

    from flow_intel.core.db import get_session, init_db
    from flow_intel.models.graph import Company
    from flow_intel.storage.repository import GraphRepository

    await init_db()

    if tickers is None:
        async with get_session() as session:
            result = await session.execute(select(Company.ticker))
            tickers = [r[0] for r in result.all()]

    results: dict[str, int] = {}

    async with RateLimitedClient() as http:
        for ticker in tickers:
            try:
                members = await fetch_board(http, ticker)
                async with get_session() as session:
                    repo = GraphRepository(session)
                    upsert_result = await repo.upsert_management_roles(ticker, members)
                results[ticker] = upsert_result.inserted
            except Exception as exc:
                _log.warning("company_scrape_failed", ticker=ticker, error=str(exc))
                results[ticker] = 0

    # Refresh materialized view after all inserts
    async with get_session() as session:
        await session.execute(
            text("REFRESH MATERIALIZED VIEW CONCURRENTLY board_interlocks")
        )
        _log.info("board_interlocks_refreshed")

    return results
