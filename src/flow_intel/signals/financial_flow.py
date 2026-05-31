"""Financial flow analysis: related-party disclosures and public tender records.

PoC scope — RALYH/KAPLM/Hera Teknik/Ral Enerji cluster only.
Language rule: neutral reporting only. Use 'beyan edilen', 'kamuya açıklanan'.
Forbidden: 'gizli ortak', 'asset transfer', 'saptanmıştır', 'kartel'.

ADIM 1a recon result (2026-05-30):
  KAP API provides FR-class financial reports but relatedStocks=None for all FR items.
  Company-level ticker filtering at list-API stage is not possible without fetching
  each disclosure's detail (~800+ items per quarter). Current scraper architecture
  does not support this. Conclusion: ADIM 1b (LLM extraction) skipped; function
  returns NONE match finding as the documented negative result.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class RelatedPartyFinding:
    source_company: str
    counterparty: str | None
    transaction_type: str | None
    amount_try: Decimal | None
    period: str | None
    disclosure_url: str
    raw_excerpt: str
    match_method: str  # "NAMED" | "AGGREGATE_ONLY" | "NONE"

    def __post_init__(self) -> None:
        if self.match_method not in ("NAMED", "AGGREGATE_ONLY", "NONE"):
            raise ValueError(f"Invalid match_method: {self.match_method!r}")


@dataclass
class TenderFinding:
    company: str
    tender_authority: str | None
    tender_subject: str | None
    amount_try: Decimal | None
    date: str | None
    source_url: str  # REQUIRED — no entry without a verifiable URL

    def __post_init__(self) -> None:
        if not self.source_url or not self.source_url.strip():
            raise ValueError("TenderFinding.source_url is required")


async def fetch_related_party_disclosures(
    ticker: str,
) -> list[RelatedPartyFinding]:
    """Attempt to retrieve related-party disclosure footnotes from KAP FR reports.

    Current status: ADIM 1a BLOCKING — KAP list API returns FR disclosures with
    relatedStocks=None, making company-level filtering impractical at PoC scale.
    Returns a single NONE-match finding as the documented negative result.

    When this limitation is resolved (dedicated FR scraper), this function should:
      1. Query KAP list endpoint for FR-class disclosures in the relevant quarter
      2. Fetch detail for each FR disclosure to find the correct ticker
      3. Download and extract PDF/HTML with pdfminer
      4. Search for 'ilişkili taraf' section and extract counterparty / amount rows
    """
    return [
        RelatedPartyFinding(
            source_company=ticker,
            counterparty=None,
            transaction_type=None,
            amount_try=None,
            period=None,
            disclosure_url=f"https://www.kap.org.tr/tr/sirket-bilgileri/ozet/{ticker}",
            raw_excerpt=(
                "KAP finansal rapor dipnotu bu sürümde çekilemedi. "
                "Sebep: KAP list API FR class bildirimlerde relatedStocks=None — "
                "şirket bazlı filtreleme mevcut altyapıyla mümkün değil."
            ),
            match_method="NONE",
        )
    ]


def build_management_bridges(actor_footprints: list) -> list[dict]:
    """Build person ↔ listed ↔ unlisted company bridge rows from existing footprint data.

    No new DB queries — derived from ActorFootprint.listed_companies and
    ActorFootprint.unlisted_companies already populated by get_actor_footprint().
    Returns list of {person, listed, unlisted} dicts for template rendering.
    """
    bridges: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for fp in actor_footprints:
        person = fp.full_name
        listed_names = [lc.get("company_name", lc.get("ticker", "")) for lc in fp.listed_companies]
        for uc in fp.unlisted_companies:
            unlisted_name = uc.get("name", "")
            for listed_name in listed_names:
                key = (person, listed_name, unlisted_name)
                if key not in seen:
                    seen.add(key)
                    bridges.append(
                        {"person": person, "listed": listed_name, "unlisted": unlisted_name}
                    )

    return bridges
