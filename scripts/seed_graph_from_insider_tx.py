"""Bootstrap persons, companies, person_company_roles from kap_insider_transactions.

This seed is intentionally incomplete - only insiders who made transactions appear.
TASK-005-B enriches with KAP management board disclosures (source='KAP_YONETIM').
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Allow running as a script from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

load_dotenv()

# Generic KAP platform title returned by companyTitle API field for many companies.
# Must not be persisted - it overwrites real company names on every seed run.
_GENERIC_COMPANY_TITLES: frozenset[str] = frozenset({"KAMUYU AYDINLATMA PLATFORMU"})


def _resolve_company_name(
    ticker: str,
    raw_name: str | None,
    known_names: dict[str, str],
) -> str | None:
    """Best company name for ticker; None means skip (omit from seed).

    Priority: YAML override > API-derived name (if not generic).
    """
    override = known_names.get(ticker)
    if override is not None:
        return override
    cleaned = (raw_name or "").strip()
    return cleaned if cleaned and cleaned.upper() not in _GENERIC_COMPANY_TITLES else None


from trailing_edge.scrapers.kap.helpers import (  # noqa: E402
    infer_is_independent,
    infer_role_type,
    normalize_name,
)


async def main() -> None:
    from sqlalchemy import func, select, text
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from trailing_edge.core.db import get_session, init_db
    from trailing_edge.models.graph import Company, Person, PersonCompanyRole
    from trailing_edge.models.kap import KapDisclosure, KapInsiderTransaction

    await init_db()

    # Load known company name overrides (prevents generic API title from persisting)
    yaml_path = Path(__file__).resolve().parent.parent / "config" / "known_companies.yaml"
    known_names: dict[str, str] = {}
    if yaml_path.exists():
        with open(yaml_path, encoding="utf-8") as _f:
            known_names = yaml.safe_load(_f).get("companies", {}) or {}

    async with get_session() as session:
        # Step 1 - persons (skip legal entities)
        names_result = await session.execute(
            select(KapInsiderTransaction.insider_name)
            .where(KapInsiderTransaction.is_legal_entity.is_(False))
            .distinct()
        )
        raw_names = [r[0] for r in names_result.all()]

        person_rows = [
            {"full_name": name, "name_normalized": normalize_name(name)}
            for name in raw_names
            if name and name.strip()
        ]
        if person_rows:
            await session.execute(
                pg_insert(Person.__table__)
                .values(person_rows)
                .on_conflict_do_nothing(constraint="uq_person_name")
            )

        # Step 2 - companies (YAML override applied; generic API titles filtered out)
        company_result = await session.execute(
            select(
                KapInsiderTransaction.ticker,
                func.max(KapDisclosure.company_name).label("company_name"),
            )
            .join(KapDisclosure, KapDisclosure.id == KapInsiderTransaction.disclosure_id)
            .group_by(KapInsiderTransaction.ticker)
        )
        company_rows = []
        seen_tickers: set[str] = set()
        for r in company_result.all():
            name = _resolve_company_name(r.ticker, r.company_name, known_names)
            if name:
                company_rows.append({"ticker": r.ticker, "company_name": name})
                seen_tickers.add(r.ticker)
        # Ensure YAML-known tickers are always present, even if absent from kap_disclosures
        for _ticker, _name in known_names.items():
            if _ticker not in seen_tickers:
                company_rows.append({"ticker": _ticker, "company_name": _name})
        if company_rows:
            await session.execute(
                pg_insert(Company.__table__)
                .values(company_rows)
                .on_conflict_do_update(
                    constraint="uq_company_ticker",
                    set_={"company_name": pg_insert(Company.__table__).excluded.company_name,
                          "updated_at": text("NOW()")},
                )
            )

        # Build lookup maps (name_normalized → person_id, ticker → company_id)
        person_map_result = await session.execute(
            select(Person.name_normalized, Person.id)
        )
        person_map: dict[str, int] = {r[0]: r[1] for r in person_map_result.all()}

        company_map_result = await session.execute(
            select(Company.ticker, Company.id)
        )
        company_map: dict[str, int] = {r[0]: r[1] for r in company_map_result.all()}

        # Step 3 - person_company_roles
        role_result = await session.execute(
            select(
                KapInsiderTransaction.insider_name,
                KapInsiderTransaction.ticker,
                func.max(KapInsiderTransaction.insider_role).label("role"),
                func.min(KapInsiderTransaction.transaction_date).label("valid_from"),
            )
            .where(KapInsiderTransaction.is_legal_entity.is_(False))
            .group_by(
                KapInsiderTransaction.insider_name,
                KapInsiderTransaction.ticker,
            )
        )

        pcr_rows = []
        for r in role_result.all():
            norm = normalize_name(r.insider_name)
            person_id = person_map.get(norm)
            company_id = company_map.get(r.ticker)
            if person_id is None or company_id is None:
                continue
            pcr_rows.append({
                "person_id": person_id,
                "company_id": company_id,
                "role": r.role,
                "role_type": infer_role_type(r.role),
                "is_independent": infer_is_independent(r.role),
                "source": "KAP_INSIDER_TX",
                "valid_from": r.valid_from,
                "valid_until": None,
            })

        if pcr_rows:
            await session.execute(
                pg_insert(PersonCompanyRole.__table__)
                .values(pcr_rows)
                .on_conflict_do_nothing(constraint="uq_person_company_role")
            )

        # Step 4 - refresh materialized view
        await session.execute(
            text("REFRESH MATERIALIZED VIEW CONCURRENTLY board_interlocks")
        )

        # Step 5 - summary
        n_persons = (await session.execute(
            select(func.count()).select_from(Person)
        )).scalar()
        n_companies = (await session.execute(
            select(func.count()).select_from(Company)
        )).scalar()
        n_pcr = (await session.execute(
            select(func.count()).select_from(PersonCompanyRole)
        )).scalar()
        n_interlocks = (await session.execute(
            text("SELECT COUNT(*) FROM board_interlocks")
        )).scalar()

    print(f"persons:              {n_persons}")
    print(f"companies:            {n_companies}")
    print(f"person_company_roles: {n_pcr}")
    print(f"board_interlocks:     {n_interlocks}  (persons active at >=2 companies)")


if __name__ == "__main__":
    asyncio.run(main())
