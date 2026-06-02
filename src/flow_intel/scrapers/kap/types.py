"""Pydantic DTOs and enums for KAP scraper."""
import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel


@dataclass
class BoardMemberDTO:
    full_name: str
    role: str | None
    role_type: str
    is_independent: bool
    valid_from: date | None = field(default=None)


class RelationType(str, Enum):
    KENDISI = "KENDISI"
    YAKINI = "YAKINI"
    ILISKILI_TUZEL_KISI = "ILISKILI_TUZEL_KISI"


class KapDisclosureDTO(BaseModel):
    kap_disclosure_id: str
    ticker: str
    company_name: str
    disclosure_type: str
    disclosure_subtype: str | None = None
    disclosure_class: str
    published_at: datetime | None = None
    is_correction: bool = False
    source_url: str
    raw_html: str | None = None
    raw_json: dict[str, Any] | None = None


class KapInsiderTxDTO(BaseModel):
    insider_name: str
    insider_role: str | None = None
    relation_type: str
    is_legal_entity: bool = False
    ticker: str
    transaction_date: date
    transaction_type: str
    share_count: Decimal
    price_try: Decimal | None = None
    total_value_try: Decimal | None = None
    currency: str = "TRY"
    post_tx_share_count: Decimal | None = None
    post_tx_ownership_pct: Decimal | None = None
    transaction_venue: str | None = None
    notes: str | None = None
    natural_key_hash: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.natural_key_hash:
            self.natural_key_hash = compute_natural_key_hash(
                self.insider_name,
                self.transaction_date,
                self.transaction_type,
                self.share_count,
                self.price_try,
            )


def compute_natural_key_hash(
    insider_name: str,
    transaction_date: date,
    transaction_type: str,
    share_count: Decimal,
    price_try: Decimal | None,
) -> str:
    raw = (
        f"{insider_name}|{transaction_date.isoformat()}"
        f"|{transaction_type}|{share_count}|{price_try or 'NA'}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()
