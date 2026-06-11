# Architecture

## Overview

`trailingedge` is an async Python service that scrapes publicly disclosed insider
transactions from KAP (kap.org.tr), stores them idempotently in PostgreSQL, and is
designed to serve ranked insider-flow signal reports (Phase 2).

## Data Flow

```
KAP API
  │
  ├─ POST /tr/api/disclosure/members/byCriteria  ──► KapClient.fetch_disclosure_list()
  │                                                         │
  │                                                         ▼ (filter: DKB class only)
  ├─ GET /tr/api/notification/attachment-detail/{idx} ──► KapClient.fetch_disclosure_detail()
  │                                                         │
  │                                          ┌─────────────┤
  │                                          ▼             ▼
  │                                        DKB            ODA
  │                                         │              │
  ├─ GET /tr/api/file/download/{objId} ──► PDF           HTML
  │    (Java-serialized byte[] unwrap)      │              │
  │                                         ▼             ▼
  │                                    parse_dkb_  parse_oda_
  │                                    transactions transactions
  │                                         │              │
  │                                         └──────┬───────┘
  │                                                ▼
  │                                       KapInsiderTxDTO[]
  │                                                │
  │                                                ▼
  │                                       KapRepository
  │                                    (upsert_disclosure +
  │                                     upsert_transactions)
  │                                                │
  │                                                ▼
  │                                          PostgreSQL
  │                                   kap_disclosures
  │                                   kap_insider_transactions
  │                                   scraper_runs (audit)
  │
  └─ GET /tr/bildirim-sorgu  ──► KapClient.warmup()  (WAF session cookie)
```

## Key Design Decisions

### Dual DKB/ODA Parse Path
KAP publishes two classes of insider disclosure. DKB (SPK II-15.1 forms filed by
KAP on behalf of insiders) contain transaction data exclusively in a PDF attachment.
ODA (portfolio manager filings) embed transaction tables in the HTML body. Both are
ingested to `kap_disclosures` but only DKB transactions are parsed into
`kap_insider_transactions` in Phase 1; ODA parsing is Phase 2.

### Java-Wrapped PDF
The `/file/download/{objId}` endpoint returns a Java-serialized `byte[]`, not a raw
PDF. The PDF length is stored as a 4-byte big-endian integer at bytes 23-26, and
the PDF content starts at byte 27. `KapClient.unwrap_java_pdf()` performs this
extraction.

### Idempotency via `natural_key_hash`
Each transaction row carries a SHA-256 hash over
`{name}|{date}|{type}|{count}|{price}`. The `(disclosure_id, natural_key_hash)`
pair has a UNIQUE constraint. `upsert_transactions` uses `ON CONFLICT DO NOTHING`,
so running the scraper twice over the same date range produces identical DB state.

### Audit via `scraper_runs`
Every scraper invocation writes a `scraper_runs` row (status=RUNNING at start,
SUCCESS/FAILED at end) with counts of seen/inserted/updated/skipped records.

### Rate Limiting
`RateLimitedClient` uses `aiolimiter.AsyncLimiter` at the configured RPS cap
(default 2 req/s). `tenacity` wraps each request with exponential backoff on 429,
503, `ConnectError`, and `ReadTimeout`.
