"""Add price_history, insider_clusters, signal_outcomes tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-28
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_history",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(50), nullable=False),
        sa.Column("price_date", sa.Date, nullable=False),
        sa.Column("open_try", sa.Numeric(20, 4)),
        sa.Column("high_try", sa.Numeric(20, 4)),
        sa.Column("low_try", sa.Numeric(20, 4)),
        sa.Column("close_try", sa.Numeric(20, 4), nullable=False),
        sa.Column("volume", sa.BigInteger),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("ticker", "price_date", name="uq_price_ticker_date"),
    )
    op.create_index("idx_price_ticker_date", "price_history", ["ticker", "price_date"])

    op.create_table(
        "insider_clusters",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(50), nullable=False),
        sa.Column("window_start", sa.Date, nullable=False),
        sa.Column("window_end", sa.Date, nullable=False),
        sa.Column("insider_count", sa.Integer, nullable=False),
        sa.Column("unique_insiders", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("total_buy_value_try", sa.Numeric(24, 2)),
        sa.Column("cluster_score", sa.Numeric(8, 4), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "ticker", "window_start", "window_end", name="uq_cluster_ticker_window"
        ),
    )
    op.create_index("idx_cluster_ticker", "insider_clusters", ["ticker"])
    op.create_index("idx_cluster_detected", "insider_clusters", ["detected_at"])
    op.create_index("idx_cluster_score", "insider_clusters", ["cluster_score"])

    op.create_table(
        "signal_outcomes",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "cluster_id",
            sa.BigInteger,
            sa.ForeignKey("insider_clusters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("horizon_days", sa.Integer, nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 4)),
        sa.Column("exit_price", sa.Numeric(20, 4)),
        sa.Column("return_pct", sa.Numeric(10, 4)),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("cluster_id", "horizon_days", name="uq_outcome_cluster_horizon"),
    )


def downgrade() -> None:
    op.drop_table("signal_outcomes")
    op.drop_index("idx_cluster_score", "insider_clusters")
    op.drop_index("idx_cluster_detected", "insider_clusters")
    op.drop_index("idx_cluster_ticker", "insider_clusters")
    op.drop_table("insider_clusters")
    op.drop_index("idx_price_ticker_date", "price_history")
    op.drop_table("price_history")
