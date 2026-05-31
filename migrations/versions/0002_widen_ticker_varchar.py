"""Widen ticker column from VARCHAR(20) to VARCHAR(50).

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "kap_disclosures",
        "ticker",
        existing_type=sa.String(20),
        type_=sa.String(50),
        existing_nullable=False,
    )
    op.alter_column(
        "kap_insider_transactions",
        "ticker",
        existing_type=sa.String(20),
        type_=sa.String(50),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "kap_insider_transactions",
        "ticker",
        existing_type=sa.String(50),
        type_=sa.String(20),
        existing_nullable=False,
    )
    op.alter_column(
        "kap_disclosures",
        "ticker",
        existing_type=sa.String(50),
        type_=sa.String(20),
        existing_nullable=False,
    )
