"""Initial schema: kap_disclosures, kap_insider_transactions, scraper_runs.

Revision ID: 0001
Revises:
Create Date: 2026-05-28
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE kap_disclosures (
            id                      BIGSERIAL PRIMARY KEY,
            kap_disclosure_id       VARCHAR(50)   NOT NULL UNIQUE,
            ticker                  VARCHAR(20)   NOT NULL,
            company_name            TEXT          NOT NULL,
            disclosure_type         VARCHAR(255)  NOT NULL,
            disclosure_subtype      VARCHAR(255),
            disclosure_class        VARCHAR(10)   NOT NULL,
            published_at            TIMESTAMPTZ   NOT NULL,
            is_correction           BOOLEAN       NOT NULL DEFAULT FALSE,
            corrects_disclosure_id  BIGINT        REFERENCES kap_disclosures(id),
            source_url              TEXT          NOT NULL,
            raw_html                TEXT,
            raw_json                JSONB,
            ingested_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ   NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_kap_disc_ticker    ON kap_disclosures(ticker)")
    op.execute("CREATE INDEX idx_kap_disc_published ON kap_disclosures(published_at DESC)")
    op.execute("CREATE INDEX idx_kap_disc_class     ON kap_disclosures(disclosure_class)")

    op.execute("""
        CREATE TABLE kap_insider_transactions (
            id                      BIGSERIAL PRIMARY KEY,
            disclosure_id           BIGINT        NOT NULL REFERENCES kap_disclosures(id) ON DELETE CASCADE,
            insider_name            TEXT          NOT NULL,
            insider_role            TEXT,
            relation_type           VARCHAR(30)   NOT NULL,
            is_legal_entity         BOOLEAN       NOT NULL DEFAULT FALSE,
            ticker                  VARCHAR(20)   NOT NULL,
            transaction_date        DATE          NOT NULL,
            transaction_type        VARCHAR(10)   NOT NULL,
            share_count             NUMERIC(20,2) NOT NULL,
            price_try               NUMERIC(20,4),
            total_value_try         NUMERIC(24,2),
            currency                CHAR(3)       NOT NULL DEFAULT 'TRY',
            post_tx_share_count     NUMERIC(20,2),
            post_tx_ownership_pct   NUMERIC(7,4),
            transaction_venue       VARCHAR(50),
            notes                   TEXT,
            natural_key_hash        CHAR(64)      NOT NULL,
            ingested_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_tx_type   CHECK (transaction_type IN ('BUY','SELL')),
            CONSTRAINT uq_insider_tx UNIQUE (disclosure_id, natural_key_hash)
        )
    """)
    op.execute(
        "CREATE INDEX idx_insider_tx_ticker_date ON kap_insider_transactions(ticker, transaction_date DESC)"
    )
    op.execute(
        "CREATE INDEX idx_insider_tx_name        ON kap_insider_transactions(insider_name)"
    )
    op.execute(
        "CREATE INDEX idx_insider_tx_type_date   ON kap_insider_transactions(transaction_type, transaction_date DESC)"
    )

    op.execute("""
        CREATE TABLE scraper_runs (
            id               BIGSERIAL PRIMARY KEY,
            scraper_name     VARCHAR(100) NOT NULL,
            started_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            finished_at      TIMESTAMPTZ,
            status           VARCHAR(20)  NOT NULL DEFAULT 'RUNNING',
            records_seen     INT          DEFAULT 0,
            records_inserted INT          DEFAULT 0,
            records_updated  INT          DEFAULT 0,
            records_skipped  INT          DEFAULT 0,
            error_message    TEXT,
            metadata         JSONB,
            CONSTRAINT chk_run_status CHECK (status IN ('RUNNING','SUCCESS','FAILED','PARTIAL'))
        )
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_kap_disc_upd
            BEFORE UPDATE ON kap_disclosures
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER trg_insider_tx_upd
            BEFORE UPDATE ON kap_insider_transactions
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_insider_tx_upd ON kap_insider_transactions")
    op.execute("DROP TRIGGER IF EXISTS trg_kap_disc_upd ON kap_disclosures")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.execute("DROP TABLE IF EXISTS scraper_runs")
    op.execute("DROP TABLE IF EXISTS kap_insider_transactions")
    op.execute("DROP TABLE IF EXISTS kap_disclosures")
