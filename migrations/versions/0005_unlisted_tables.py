"""Add unlisted_companies and person_unlisted_roles tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "unlisted_companies",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("name_normalized", sa.Text, nullable=False),
        sa.Column("sicil_no", sa.String(50)),
        sa.Column("mersis_no", sa.String(20)),
        sa.Column("city", sa.String(100)),
        sa.Column("district", sa.String(100)),
        sa.Column("nace_code", sa.String(20)),
        sa.Column("company_type", sa.String(30)),
        sa.Column("founded_date", sa.Date),
        sa.Column("gazette_issue", sa.String(50)),
        sa.Column("source_url", sa.Text),
        sa.Column("raw_text", sa.Text),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("sicil_no", name="uq_unlisted_sicil"),
        sa.UniqueConstraint("mersis_no", name="uq_unlisted_mersis"),
    )
    op.create_index("idx_unlisted_name_norm", "unlisted_companies", ["name_normalized"])
    op.create_index("idx_unlisted_city", "unlisted_companies", ["city"])
    op.execute("CREATE INDEX idx_unlisted_founded ON unlisted_companies(founded_date DESC)")

    op.create_table(
        "person_unlisted_roles",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("person_id", sa.BigInteger, sa.ForeignKey("persons.id")),
        sa.Column("raw_person_name", sa.Text, nullable=False),
        sa.Column(
            "unlisted_company_id",
            sa.BigInteger,
            sa.ForeignKey("unlisted_companies.id"),
            nullable=False,
        ),
        sa.Column("role", sa.Text),
        sa.Column("role_type", sa.String(30), nullable=False, server_default="FOUNDER"),
        sa.Column("match_confidence", sa.Numeric(4, 3)),
        sa.Column("match_method", sa.String(30)),
        sa.Column("valid_from", sa.Date),
        sa.Column("valid_until", sa.Date),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "raw_person_name", "unlisted_company_id", "role_type",
            name="uq_person_unlisted_role",
        ),
    )
    op.create_index("idx_pur_person_id", "person_unlisted_roles", ["person_id"])
    op.create_index("idx_pur_company", "person_unlisted_roles", ["unlisted_company_id"])
    op.execute(
        "CREATE INDEX idx_pur_confidence ON person_unlisted_roles(match_confidence DESC)"
    )
    op.create_index("idx_pur_raw_name", "person_unlisted_roles", ["raw_person_name"])


def downgrade() -> None:
    op.drop_table("person_unlisted_roles")
    op.drop_table("unlisted_companies")
