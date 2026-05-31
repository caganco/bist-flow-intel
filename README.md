# bist-flow-intel

> **Asynchronous Python data engine that ingests SPK II-15.1 insider
> transaction disclosures from KAP (kap.org.tr), measures empirical
> forward returns, and produces forensic intelligence briefs on
> BIST-listed companies.**

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org)
[![PostgreSQL](https://img.shields.io/badge/postgres-16-336791.svg)](https://www.postgresql.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI](https://github.com/caganco/bist-flow-intel/actions/workflows/ci.yml/badge.svg)](https://github.com/caganco/bist-flow-intel/actions/workflows/ci.yml)

---

## What it does

- **Scrapes** Turkey's public-disclosure platform (KAP) for SPK II-15.1
  individual-insider transaction reports — Turkey's regulatory equivalent
  of SEC Form 4.
- **Reverse-engineers** KAP's undocumented Java-serialized `byte[]` PDF
  wrapper, parses the DKB transaction tables (Turkish-locale numbers,
  Windows-1252 encoded), and stores normalised rows in PostgreSQL with
  cryptographic deduplication.
- **Measures empirical forward returns** (5/20/60 trading-day horizons)
  over detected insider-cluster events, computing hit rate, median, and
  best/worst outcomes — a transparent, replayable base-rate framework.
- **Generates forensic briefs** (HTML + PDF) per BIST ticker, combining
  insider-transaction history, board-interlock graphs, and (optionally)
  Türkiye Ticaret Sicil Gazetesi cross-references.

## Türkçe özet

`bist-flow-intel`, BIST'in **SPK II-15.1 (Pay Alım Satım Bildirimi)**
kapsamındaki şirket-içi alım-satım bildirimlerini KAP üzerinden çekip
PostgreSQL'e yazan, üzerine **ileriye dönük getiri ölçümü** ve
**şirket-bazlı forensic rapor** üreten bir veri-mühendisliği projesidir.
ABD'deki SEC Form 4 takipçilerinin (ör. OpenInsider) Türk sermaye
piyasaları için **referans implementasyonu** olarak tasarlandı: şeffaf,
yeniden üretilebilir, audit-trail'li, açık kaynak.

## Why this matters

KAP — operated by **Merkezi Kayıt Kuruluşu (MKK)** under Türkiye's capital
markets framework — exposes the entire insider-disclosure feed publicly,
yet there is no open analytical layer comparable to U.S. SEC Form 4
trackers. `bist-flow-intel` fills that gap: a transparent, audit-logged,
reproducible pipeline that any regulator, researcher, or market
participant can stand up locally in under thirty minutes.

The project also serves as a working reference for several
non-trivial integration problems:

- KAP's undocumented Java object-serialization wrapper around PDF downloads
- Turkish-locale numeric / date / encoding handling in `pdfminer`
- Idempotent disclosure ingest under a 2,000-record API cap with
  windowed pagination
- Forensic graph analytics over board-interlock data via NetworkX

## Quick start

```bash
cp .env.example .env          # set DATABASE_URL and KAP_BASE_URL
docker-compose up -d          # postgres
uv sync                       # python deps
alembic upgrade head          # schema
```

Daily ingest:

```bash
flow-intel scrape kap-insider --last-hours 24      # last day
flow-intel scrape kap-insider --last-hours 168     # last week
flow-intel scrape kap-insider --since 2026-05-01 --until 2026-05-27
```

Forensic brief for a single ticker:

```bash
flow-intel report forensic KAPLM
```

## Sample output — daily signal

`reports/daily/2026-05-28_signal.json` (excerpt):

```json
{
  "as_of_date": "2026-05-28",
  "clusters": [
    {
      "ticker": "SARKY",
      "cluster_score": 42.83,
      "insider_count": 2,
      "window_start": "2026-05-21",
      "window_end": "2026-05-21",
      "unique_insiders": ["HAMİT MÜCELLİT", "SEVGÜR ARSLANPAY"],
      "total_buy_value_try": 711360.0
    }
  ],
  "base_rates": {
    "5":  { "hit_rate_pct": 44.83, "median_return_pct": -1.87, "signals_with_outcome": 29 },
    "20": { "hit_rate_pct": 55.17, "median_return_pct":  3.81, "signals_with_outcome": 29 },
    "60": { "hit_rate_pct": 52.17, "median_return_pct":  0.61, "signals_with_outcome": 23 }
  }
}
```

Forward returns are measured empirically against actual BIST closes from
`yfinance` — no synthetic benchmarks, no curve-fitting. Sample sizes are
intentionally exposed so consumers can judge statistical significance.

## Technical highlights

| Concern | Implementation |
|---|---|
| HTTP | `httpx` async + `aiolimiter` (2 RPS cap) + `tenacity` retry on 429/503/timeout |
| PDF unwrap | Java `byte[]` serialization stripped at offset 23 (4-byte BE length prefix) |
| PDF parse | `pdfminer.six` with Windows-1252 awareness; date-anchored row extraction |
| Number parse | `1.234,56` → `Decimal("1234.56")` with explicit sign handling |
| Idempotency | `SHA-256(name\|date\|type\|count\|price)` natural key + `ON CONFLICT DO NOTHING` |
| Audit | `scraper_runs` table with `RUNNING → SUCCESS/FAILED/PARTIAL` state machine |
| Schema | SQLAlchemy 2.0 typed `Mapped[...]` ORM + Alembic migrations |
| Pagination | 2,000-record API cap handled via configurable date windows |
| Names | `rapidfuzz token_sort_ratio` + Turkish ASCII transliteration for cross-source joins |
| Graph | NetworkX over `board_interlocks` materialised view with `REFRESH CONCURRENTLY` |
| OCR (optional) | PyMuPDF render @ 300 DPI → Tesseract `-l tur` for Ticaret Sicil gazettes |

## Architecture

```
KAP API
  └─ POST /tr/api/disclosure/members/byCriteria  ──► list (filter DKB)
  └─ GET  /tr/api/notification/attachment-detail ──► detail + objId
  └─ GET  /tr/api/file/download/{objId}          ──► PDF (Java-wrapped)
                                                     │
                                                     ▼
                              parse_dkb_transactions (pdfminer)
                                                     │
                                                     ▼
                                            KapRepository
                                       (upsert disclosure + txs)
                                                     │
                                                     ▼
                                              PostgreSQL
                                                     │
              ┌──────────────────────┬───────────────┴──────────────────┐
              ▼                      ▼                                  ▼
       cluster detection      forward returns                 forensic brief
       (≥N insiders, Δt)      (5/20/60-day horizons)          (HTML + PDF)
```

Detailed data flow, design decisions, and Turkish-locale edge cases:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md),
[`docs/KAP_ENDPOINT_NOTES.md`](docs/KAP_ENDPOINT_NOTES.md).

## Project structure

```
src/flow_intel/
  core/        config, logging, async http client, db, tz helpers
  scrapers/
    kap/       KAP HTTP client + DKB/ODA parser + orchestrator
    ticaret_sicil/   CAPTCHA-gated TSG client + OCR pipeline (optional)
  models/      SQLAlchemy ORM (disclosures, transactions, graph, signal)
  storage/     repository / upsert layer
  signals/     cluster detection, forward returns, base rates, graph
  reports/     daily signal, forensic brief, network, cross-reference
  data/        yfinance price ingest
  cli/         click entrypoint (flow-intel ...)

docs/          architecture, data dictionary, KAP endpoint reconnaissance
scripts/       backfill, fixture acquisition, ops scripts
migrations/    alembic
tests/         unit/ (no DB) and integration/ (TEST_DATABASE_URL)
```

## Testing

```bash
uv run pytest tests/unit/ -v          # no DB required
uv run pytest tests/integration/ -v   # requires TEST_DATABASE_URL
```

## Known limitations

These are documented openly so consumers can judge the analytics layer
honestly:

- **Disclosure timing.** `transaction_date` in the PDF can pre-date the
  `published_at` of the KAP filing by several days. The current
  cluster-return measurement uses `window_end` (= last transaction date)
  as the entry-price anchor. Strict point-in-time backtesting should
  instead use `max(transaction_date, published_at)` to avoid leaking the
  filing date forward — tracked for the next analytics revision.
- **Sample size.** Forward-return base rates are computed over a
  small (~30-signal) live window. A historical backfill is required
  before the numbers can be treated as anything stronger than
  *indicative*.
- **Excess returns.** Returns are absolute, not benchmarked against the
  XU100 index. An excess-over-benchmark view is straightforward to add
  but out of scope for the current phase.
- **ODA disclosures.** Fund-company threshold-crossing reports (Article 12)
  are stored at the disclosure level but not yet parsed into the
  transaction table.
- **TSG OCR.** The Türkiye Ticaret Sicil Gazetesi pipeline is
  CAPTCHA-gated (semi-automatic) and intended for forensic enrichment,
  not for any market-signal claim.

## Status

Phase 1 — working end-to-end pipeline (ingest + analytics + briefs) on
a single-node deployment. Production hardening (HA Postgres, scheduled
ingest, alerting) is out of scope for this revision.

## License

[MIT](LICENSE)
