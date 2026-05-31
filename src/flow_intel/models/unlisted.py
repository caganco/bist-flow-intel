"""ORM models for unlisted company ingestion (Ticaret Sicil)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flow_intel.models.base import Base


class UnlistedCompany(Base):
    __tablename__ = "unlisted_companies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    sicil_no: Mapped[str | None] = mapped_column(String(50))
    mersis_no: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100))
    nace_code: Mapped[str | None] = mapped_column(String(20))
    company_type: Mapped[str | None] = mapped_column(String(30))
    founded_date: Mapped[date | None] = mapped_column(Date)
    gazette_issue: Mapped[str | None] = mapped_column(String(50))
    source_url: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    roles: Mapped[list["PersonUnlistedRole"]] = relationship(back_populates="company")


class PersonUnlistedRole(Base):
    __tablename__ = "person_unlisted_roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    person_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("persons.id"))
    raw_person_name: Mapped[str] = mapped_column(Text, nullable=False)
    unlisted_company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("unlisted_companies.id"), nullable=False
    )
    role: Mapped[str | None] = mapped_column(Text)
    role_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default="FOUNDER")
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    match_method: Mapped[str | None] = mapped_column(String(30))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    company: Mapped["UnlistedCompany"] = relationship(back_populates="roles")
