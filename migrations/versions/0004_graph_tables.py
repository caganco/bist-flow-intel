"""Add persons, companies, person_company_roles tables and board_interlocks view.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "persons",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("full_name", sa.Text, nullable=False),
        sa.Column("name_normalized", sa.Text, nullable=False),
        sa.UniqueConstraint("name_normalized", name="uq_person_name"),
    )

    op.create_table(
        "companies",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(50), nullable=False),
        sa.Column("company_name", sa.Text, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("ticker", name="uq_company_ticker"),
    )

    op.create_table(
        "person_company_roles",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("person_id", sa.BigInteger, sa.ForeignKey("persons.id"), nullable=False),
        sa.Column("company_id", sa.BigInteger, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("role", sa.Text),
        sa.Column("role_type", sa.String(30), nullable=False),
        sa.Column("is_independent", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("valid_from", sa.Date),
        sa.Column("valid_until", sa.Date),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "person_id", "company_id", "role_type", "valid_from",
            name="uq_person_company_role",
        ),
    )
    op.create_index("idx_pcr_person",    "person_company_roles", ["person_id"])
    op.create_index("idx_pcr_company",   "person_company_roles", ["company_id"])
    op.create_index("idx_pcr_role_type", "person_company_roles", ["role_type"])

    op.execute("""
        CREATE MATERIALIZED VIEW board_interlocks AS
        SELECT
            p.id                AS person_id,
            p.full_name         AS person_name,
            c1.ticker           AS company_a,
            c2.ticker           AS company_b,
            pcr1.role           AS role_in_a,
            pcr2.role           AS role_in_b,
            pcr1.is_independent AS is_independent_a
        FROM person_company_roles pcr1
        JOIN person_company_roles pcr2
            ON  pcr1.person_id  = pcr2.person_id
            AND pcr1.company_id < pcr2.company_id
            AND pcr1.valid_until IS NULL
            AND pcr2.valid_until IS NULL
        JOIN persons   p  ON p.id  = pcr1.person_id
        JOIN companies c1 ON c1.id = pcr1.company_id
        JOIN companies c2 ON c2.id = pcr2.company_id
        WITH DATA
    """)
    # UNIQUE index required for REFRESH MATERIALIZED VIEW CONCURRENTLY
    op.execute(
        "CREATE UNIQUE INDEX uq_bi_person_a_b ON board_interlocks(person_id, company_a, company_b)"
    )
    op.create_index("idx_bi_person",    "board_interlocks", ["person_id"])
    op.create_index("idx_bi_company_a", "board_interlocks", ["company_a"])
    op.create_index("idx_bi_company_b", "board_interlocks", ["company_b"])


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS board_interlocks")
    op.drop_table("person_company_roles")
    op.drop_table("companies")
    op.drop_table("persons")
