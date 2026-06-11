"""ORM models for Layer D: network graph node and edge tables."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trailing_edge.models.base import Base


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    name_normalized: Mapped[str] = mapped_column(Text, nullable=False)

    roles: Mapped[list["PersonCompanyRole"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    roles: Mapped[list["PersonCompanyRole"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class PersonCompanyRole(Base):
    __tablename__ = "person_company_roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("persons.id"), nullable=False)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False)
    role: Mapped[str | None] = mapped_column(Text)
    role_type: Mapped[str] = mapped_column(String(30), nullable=False)
    is_independent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    person: Mapped["Person"] = relationship(back_populates="roles")
    company: Mapped["Company"] = relationship(back_populates="roles")
