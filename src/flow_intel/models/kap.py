"""ORM models for KAP disclosure data."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flow_intel.models.base import Base, TimestampMixin


class KapDisclosure(Base, TimestampMixin):
    __tablename__ = "kap_disclosures"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kap_disclosure_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    disclosure_type: Mapped[str] = mapped_column(String(255), nullable=False)
    disclosure_subtype: Mapped[str | None] = mapped_column(String(255))
    disclosure_class: Mapped[str] = mapped_column(String(10), nullable=False)
    published_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    is_correction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    corrects_disclosure_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("kap_disclosures.id")
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    raw_html: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict | None] = mapped_column(JSONB)

    transactions: Mapped[list["KapInsiderTransaction"]] = relationship(
        back_populates="disclosure", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_kap_disc_ticker", "ticker"),
        Index("idx_kap_disc_published", "published_at"),
        Index("idx_kap_disc_class", "disclosure_class"),
    )


class KapInsiderTransaction(Base, TimestampMixin):
    __tablename__ = "kap_insider_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    disclosure_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("kap_disclosures.id", ondelete="CASCADE"), nullable=False
    )
    insider_name: Mapped[str] = mapped_column(Text, nullable=False)
    insider_role: Mapped[str | None] = mapped_column(Text)
    relation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    is_legal_entity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(10), nullable=False)
    share_count: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    price_try: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    total_value_try: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="TRY")
    post_tx_share_count: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    post_tx_ownership_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    transaction_venue: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    natural_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    disclosure: Mapped["KapDisclosure"] = relationship(back_populates="transactions")

    __table_args__ = (
        CheckConstraint("transaction_type IN ('BUY','SELL')", name="chk_tx_type"),
        UniqueConstraint("disclosure_id", "natural_key_hash", name="uq_insider_tx"),
        Index("idx_insider_tx_ticker_date", "ticker", "transaction_date"),
        Index("idx_insider_tx_name", "insider_name"),
        Index("idx_insider_tx_type_date", "transaction_type", "transaction_date"),
    )


class ScraperRun(Base):
    __tablename__ = "scraper_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scraper_name: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RUNNING")
    records_seen: Mapped[int] = mapped_column(Integer, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING','SUCCESS','FAILED','PARTIAL')", name="chk_run_status"
        ),
    )
