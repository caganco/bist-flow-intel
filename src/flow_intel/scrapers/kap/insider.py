"""KAP insider scraper orchestrator."""
from dataclasses import dataclass
from datetime import date

from flow_intel.core.db import get_session
from flow_intel.core.http import RateLimitedClient
from flow_intel.core.logging import get_logger
from flow_intel.scrapers.base import AbstractScraper
from flow_intel.scrapers.kap.client import KapClient
from flow_intel.scrapers.kap.parser import (
    parse_dkb_transactions,
    parse_disclosure_metadata,
    parse_oda_transactions,
)
from flow_intel.models.kap import ScraperRun
from flow_intel.storage.repository import KapRepository

_log = get_logger(__name__)

SCRAPER_NAME = "kap_insider"


@dataclass
class ScraperRunResult:
    records_seen: int
    records_inserted: int
    records_updated: int
    records_skipped: int
    status: str


class KapInsiderScraper(AbstractScraper):
    def __init__(self, *, backfill: bool = False) -> None:
        self._backfill = backfill

    async def run(self, from_date: date, to_date: date) -> ScraperRunResult:
        # Create the audit run record
        run_meta = (
            {"backfill": True, "from_date": from_date.isoformat(), "to_date": to_date.isoformat()}
            if self._backfill else None
        )
        async with get_session() as session:
            repo = KapRepository(session)
            run = await repo.create_scraper_run(SCRAPER_NAME, metadata=run_meta)
        run_id: int = run.id

        seen = inserted = updated = skipped = 0
        error_msg: str | None = None

        try:
            async with RateLimitedClient() as http:
                kap = KapClient(http)
                await kap.warmup()
                disclosures = await kap.fetch_disclosure_list(from_date, to_date)
                seen = len(disclosures)

                for disc in disclosures:
                    disclosure_index = str(disc.get("disclosureIndex", ""))
                    # Use disclosureIndex as the stable ID (list API has no disclosureId)
                    kap_disclosure_id = disclosure_index
                    is_correction = bool(disc.get("isChanged") or disc.get("isCorrection") or False)

                    async with get_session() as session:
                        repo = KapRepository(session)
                        already_exists = await repo.disclosure_exists(kap_disclosure_id)

                    if already_exists and not is_correction:
                        skipped += 1
                        _log.debug("disclosure_skipped", kap_disclosure_id=kap_disclosure_id)
                        continue

                    try:
                        detail = await kap.fetch_disclosure_detail(disclosure_index)
                        # Pass list_item so metadata uses DKB class (not detail's DUY)
                        dto = parse_disclosure_metadata(detail, list_item=disc)

                        txs = []
                        # Route by the list API's disclosureClass (reliable DKB indicator)
                        is_dkb = disc.get("disclosureClass") == "DKB"
                        if is_dkb:
                            attachments = detail.get("attachments", [])
                            if attachments:
                                obj_id = attachments[0].get("objId", "")
                                if obj_id:
                                    pdf_bytes = await kap.fetch_pdf(obj_id)
                                    txs = parse_dkb_transactions(
                                        pdf_bytes,
                                        ticker=dto.ticker,
                                        insider_name="",
                                    )
                        else:
                            body = detail.get("disclosureBody", "") or ""
                            txs = parse_oda_transactions(body, ticker=dto.ticker)


                        async with get_session() as session:
                            repo = KapRepository(session)
                            model, created = await repo.upsert_disclosure(dto)
                            result = await repo.upsert_transactions(model.id, txs)

                        if created:
                            inserted += 1
                        else:
                            updated += 1
                        inserted += result.inserted

                        _log.info(
                            "disclosure_processed",
                            kap_disclosure_id=kap_disclosure_id,
                            ticker=dto.ticker,
                            created=created,
                            tx_inserted=result.inserted,
                        )

                    except Exception as exc:
                        _log.error(
                            "disclosure_error",
                            kap_disclosure_id=kap_disclosure_id,
                            error=str(exc),
                            exc_info=True,
                        )

        except Exception as exc:
            error_msg = str(exc)
            _log.error("scraper_failed", error=error_msg, exc_info=True)
            async with get_session() as session:
                run_obj = await session.get(ScraperRun, run_id)
                if run_obj:
                    repo = KapRepository(session)
                    await repo.finish_scraper_run(
                        run_obj,
                        status="FAILED",
                        records_seen=seen,
                        records_inserted=inserted,
                        records_updated=updated,
                        records_skipped=skipped,
                        error_message=error_msg,
                    )
            raise

        async with get_session() as session:
            run_obj = await session.get(ScraperRun, run_id)
            if run_obj:
                repo = KapRepository(session)
                await repo.finish_scraper_run(
                    run_obj,
                    status="SUCCESS",
                    records_seen=seen,
                    records_inserted=inserted,
                    records_updated=updated,
                    records_skipped=skipped,
                )

        _log.info(
            "scraper_done",
            seen=seen,
            inserted=inserted,
            updated=updated,
            skipped=skipped,
        )
        return ScraperRunResult(
            records_seen=seen,
            records_inserted=inserted,
            records_updated=updated,
            records_skipped=skipped,
            status="SUCCESS",
        )
