# Data Dictionary

## Table: `kap_disclosures`

| Column | Type | Source | Transformation | Notes |
|--------|------|--------|---------------|-------|
| `id` | BIGSERIAL | - | Auto-generated PK | |
| `kap_disclosure_id` | VARCHAR(50) | `disclosureBasic.disclosureId` | Taken as-is (UUID string) | Unique; used as idempotency key |
| `ticker` | VARCHAR(20) | `disclosureBasic.relatedStocks[0].stock` | Uppercased | First related stock; DKB has exactly one |
| `company_name` | TEXT | `disclosureBasic.title` | Taken as-is | Full legal name in Turkish |
| `disclosure_type` | VARCHAR(255) | `disclosureBasic.subject` | Taken as-is | e.g. "Pay Alım Satım Bildirimi" |
| `disclosure_subtype` | VARCHAR(255) | `disclosureBasic.disclosureType` | Nullable | May be null |
| `disclosure_class` | VARCHAR(10) | `disclosureBasic.disclosureClass` | Taken as-is | "DKB" or "ODA" |
| `published_at` | TIMESTAMPTZ | `disclosureBasic.publishDate` | Parsed from "YYYY.MM.DD HH:MM:SS", localized to Europe/Istanbul | |
| `is_correction` | BOOLEAN | `disclosureBasic.isCorrection` | Boolean coercion | False when absent |
| `corrects_disclosure_id` | BIGINT FK | - | Set by application when correction links to original | Self-referential FK |
| `source_url` | TEXT | Constructed | `{base_url}/tr/bildirim/{disclosureIndex}` | Direct link to KAP disclosure page |
| `raw_html` | TEXT | `disclosureBody` | Stored as-is | May be empty for DKB class |
| `raw_json` | JSONB | Full `/attachment-detail/{idx}` response | Stored as-is | Includes basic, detail, attachments |
| `ingested_at` | TIMESTAMPTZ | - | `NOW()` at INSERT | Set by DB default |
| `updated_at` | TIMESTAMPTZ | - | `NOW()` via trigger on UPDATE | Maintained by `set_updated_at()` trigger |

---

## Table: `kap_insider_transactions`

| Column | Type | Source | Transformation | Notes |
|--------|------|--------|---------------|-------|
| `id` | BIGSERIAL | - | Auto-generated PK | |
| `disclosure_id` | BIGINT FK | - | FK to `kap_disclosures.id` | Cascades on delete |
| `insider_name` | TEXT | PDF text - "Ad Soyad" field | Extracted from DKB PDF; trimmed, uppercased | All-caps in KAP forms |
| `insider_role` | TEXT | PDF text - "Görevi" field | Nullable; blank in most self-transaction forms | |
| `relation_type` | VARCHAR(30) | PDF text - relation field block | KENDISI / YAKINI / ILISKILI_TUZEL_KISI | See heuristic below |
| `is_legal_entity` | BOOLEAN | Inferred | True when insider is a company, not a person | |
| `ticker` | VARCHAR(20) | `relatedStocks[0].stock` | Uppercased | Denormalized from disclosure |
| `transaction_date` | DATE | PDF table - "İşlem Tarihi" column | Parsed from DD/MM/YYYY | May span multiple rows if multi-date trade |
| `transaction_type` | VARCHAR(10) | PDF table - buy/sell columns | sell_nominal > 0 → SELL; buy_nominal > 0 → BUY | CHECK(IN ('BUY','SELL')) |
| `share_count` | NUMERIC(20,2) | PDF table - Alım/Satım nominal (TL) | Turkish number → Decimal; 1 TL nominal = 1 share | For stocks with 1 TL par value |
| `price_try` | NUMERIC(20,4) | PDF narrative - "X,XX - Y,YY TL fiyat aralığından" | Lower bound of price range extracted | NULL for off-market transfers |
| `total_value_try` | NUMERIC(24,2) | Computed | share_count × price_try (when both available) | May be NULL |
| `currency` | CHAR(3) | Hardcoded | Always "TRY" for KAP disclosures | |
| `post_tx_share_count` | NUMERIC(20,2) | PDF table - "Gün Sonu Nominal Tutar" column | Turkish number → Decimal | |
| `post_tx_ownership_pct` | NUMERIC(7,4) | PDF table - "Gün Sonu Bakiyesinin Sermayeye Oranı (%)" | Turkish decimal → Decimal | e.g. 19,10 → 19.10 |
| `transaction_venue` | VARCHAR(50) | - | Not yet extracted; reserved for Phase 2 | BİST normal, OTC, etc. |
| `notes` | TEXT | - | Free-text field for edge cases | |
| `natural_key_hash` | CHAR(64) | Computed | SHA-256 of `name|date|type|count|price` | Idempotency key |
| `ingested_at` | TIMESTAMPTZ | - | `NOW()` at INSERT | |
| `updated_at` | TIMESTAMPTZ | - | `NOW()` via trigger | |

### Relation Type Heuristic

The three relation fields in a DKB PDF form (Tüzel Kişi Adına, Görevi, Varsa
Birlikte Hareket Eden Kişiler) appear after three consecutive `:` markers. If the
text block between those colons and the next page break contains only whitespace
and non-breaking spaces (\\xa0), all fields are blank → `KENDISI` (the insider
is trading on their own behalf). Non-blank blocks are classified as `YAKINI`
(related natural person) or `ILISKILI_TUZEL_KISI` (related legal entity) by
keyword matching.

---

## Table: `scraper_runs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | BIGSERIAL | Auto PK |
| `scraper_name` | VARCHAR(100) | e.g. "kap_insider" |
| `started_at` | TIMESTAMPTZ | `NOW()` at INSERT |
| `finished_at` | TIMESTAMPTZ | NULL until scraper completes |
| `status` | VARCHAR(20) | RUNNING / SUCCESS / FAILED / PARTIAL |
| `records_seen` | INT | Total disclosures returned by KAP API |
| `records_inserted` | INT | New disclosures + new transactions inserted |
| `records_updated` | INT | Existing disclosures updated (corrections) |
| `records_skipped` | INT | Disclosures already in DB (idempotency) |
| `error_message` | TEXT | Exception string on FAILED status |
| `metadata` | JSONB | Reserved for structured run metadata |
