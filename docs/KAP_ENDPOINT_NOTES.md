# KAP API Endpoint Notes

> **Reconnaissance date:** 2026-05-28  
> **Researcher:** trailingedge project reconnaissance  
> **Source of truth for:** `src/trailing_edge/scrapers/kap/insider.py`

---

## 1. Platform Overview

KAP (Kamuyu Aydınlatma Platformu - Public Disclosure Platform) is operated by MKK (Merkezi
Kayıt Kuruluşu A.Ş.). The platform is a Next.js SPA fronting a JSON REST API. All public
data is available without authentication.

Base URL: `https://www.kap.org.tr`

**robots.txt status:** Returns HTTP 666 (custom WAF rejection). Not accessible via HEAD/GET.
We proceeded based on the fact that the underlying API endpoints return 200 and the data is
intended for public consumption per KAP's stated mandate.

---

## 2. Insider Transaction Disclosure Type

The scraper targets **"Pay Alım Satım Bildirimi"** (Share Buy/Sell Notification).

There are **two sub-types**:

| `disclosureClass` | `kapTitle` | Content | How to parse |
|---|---|---|---|
| `DKB` | `KAMUYU AYDINLATMA PLATFORMU` | SPK II-15.1 individual insider forms | PDF attachment (Java-serialized byte array) + disclosure body HTML |
| `ODA` | Portfolio/fund management company | Fund threshold-crossing reports (Art. 12) | Structured HTML table in `disclosureBody` |

**For the insider-activity use case, target `disclosureClass == "DKB"` disclosures.**  
ODA disclosures are major-shareholder threshold crossings by fund companies (not individual insider trades).

---

## 3. API Endpoints

### 3.1 Disclosure List - `POST /tr/api/disclosure/members/byCriteria`

**Full URL:** `https://www.kap.org.tr/tr/api/disclosure/members/byCriteria`

**Method:** POST  
**Content-Type:** `application/json`  
**Required headers:**
```
Referer: https://www.kap.org.tr/tr/bildirim-sorgu
User-Agent: trailingedge/0.1 (research)
```

**Request body:**
```json
{
  "fromDate": "YYYY-MM-DD",
  "toDate": "YYYY-MM-DD",
  "mkkMemberOidList": [],
  "subjectList": []
}
```

- `mkkMemberOidList`: empty = all companies; list of hex OID strings to filter by company
- `subjectList`: empty = all subjects; list of subject OID strings to filter by subject type
- **NOTE:** There is no `disclosureClass` filter in the request - filter client-side on response

**Response:** JSON array (no wrapping object), **capped at 2000 elements**.

**Sample response element:**
```json
{
  "publishDate": "26.05.2026 09:10:35",
  "fundCode": null,
  "kapTitle": "KAMUYU AYDINLATMA PLATFORMU",
  "isOldKap": false,
  "disclosureClass": "DKB",
  "disclosureType": "ODA",
  "disclosureCategory": "ODA",
  "summary": "Pay Alım Satım Bildirimi",
  "subject": "Pay Alım Satım Bildirimi",
  "relatedStocks": "EGEPO",
  "year": null,
  "ruleType": "-",
  "period": null,
  "disclosureIndex": 1611139,
  "isLate": false,
  "stockCodes": null,
  "hasMultiLanguageSupport": false,
  "attachmentCount": 1,
  "modifyStatus": null
}
```

**Field map:**

| API field | Type | Notes |
|---|---|---|
| `publishDate` | string | Turkish format: `DD.MM.YYYY HH:MM:SS` |
| `kapTitle` | string | Filer company name |
| `disclosureClass` | string | `DKB` = relay by KAP, `ODA` = filed by company |
| `disclosureType` | string | Typically same as `disclosureCategory` |
| `summary` | string | Short summary text, may be null |
| `subject` | string | Subject category name (Turkish) |
| `relatedStocks` | string | Comma-separated tickers; stock whose insider filed |
| `stockCodes` | string | Filer's own ticker (null for KAP-filed DKB) |
| `disclosureIndex` | int | Sequential integer, used in all detail API paths |
| `isLate` | bool | Whether disclosure was submitted late |
| `modifyStatus` | string/null | Non-null when this is a correction |
| `attachmentCount` | int | 1 for DKB, 0 for inline ODA |

**Pagination strategy:**
- API hard-caps at 2000 results. Use 1-3 day windows for normal daily polling.
- For backfill, use 7-day windows; expect 250-350 total disclosures per week (all types).
- Insider transactions specifically: ~15-20 per week across all BIST companies.

**Filter for insider transactions (client-side):**
```python
[d for d in results
 if d["subject"] == "Pay Alım Satım Bildirimi"
 and d["disclosureClass"] == "DKB"]
```

---

### 3.2 Disclosure Detail - `GET /tr/api/notification/attachment-detail/{disclosureIndex}`

**Full URL:** `https://www.kap.org.tr/tr/api/notification/attachment-detail/{disclosureIndex}`

**Method:** GET  
**Required headers:**
```
Referer: https://www.kap.org.tr/tr/Bildirim/{disclosureIndex}
User-Agent: trailingedge/0.1 (research)
```

**Response:** JSON array with one element:
```json
[{
  "disclosure": {
    "disclosureBasic": {
      "title": "Pay Alım Satım Bildirimi",
      "mkkMemberOid": "219472C133F901E0E0530A4AC92590EC",
      "companyTitle": "KAMUYU AYDINLATMA PLATFORMU",
      "stockCode": null,
      "relatedStocks": "EGEPO",
      "disclosureClass": "DKB",
      "disclosureType": "ODA",
      "disclosureCategory": "ODA",
      "publishDate": "2026.05.26 09:10:35",
      "disclosureId": "4028328c9e276fa9019e62e3e9ee3a0a",
      "disclosureIndex": 1611139,
      "summary": "Pay Alım Satım Bildirimi",
      "attachmentCount": 1,
      "isLate": false,
      "relatedDisclosureOid": null,
      "isChanged": null,
      "isBlocked": false
    },
    "disclosureDetail": {
      "memberType": "DDK"
    }
  },
  "disclosureBody": ["<table class=\"tbl_GENEL_DUYURU_GONDERIMI\">..."],
  "attachments": [
    {
      "objId": "4028328c9e276fa9019e62e3ea3b3a10",
      "fileName": "EGEPO_55470.pdf",
      "fileExtension": "pdf"
    }
  ]
}]
```

**Key fields:**
- `disclosure.disclosureBasic.disclosureId` - stable UUID-like hex string; use as `kap_disclosure_id` for upsert
- `disclosure.disclosureBasic.isChanged` - non-null when disclosure is a correction
- `disclosure.disclosureBasic.relatedDisclosureOid` - if correction, points to original disclosureId
- `disclosureBody[0]` - HTML string; for DKB = narrative only; for ODA = full taxonomy table
- `attachments[].objId` - used to download the actual PDF document

**DKB disclosureBody HTML contains:**
- `Yapılan açıklama düzeltme mi?` → Yes/No (correction flag)
- `İlgili Şirketler` → Comma-separated stock codes
- `Açıklamalar` → Narrative text that includes the **insider's name**

**ODA disclosureBody HTML contains** (class `tbl_oda-10400_Shares-Transaction-Notification`):
- `oda_UpdateAnnouncementFlag` → update flag
- `oda_CorrectionAnnouncementFlag` → correction flag
- Transaction table rows with: `İşlem Tarihi`, buy nominal (TL), sell nominal (TL),
  net nominal, start/end holdings, ownership percentages

---

### 3.3 PDF Attachment Download - `GET /tr/api/file/download/{objId}`

**Full URL:** `https://www.kap.org.tr/tr/api/file/download/{objId}`

**Method:** GET  
**Required headers:** same Referer as detail endpoint

**⚠️ QUIRK - Java Serialized Byte Array Wrapper:**  
The response is NOT a raw PDF. It is a **Java-serialized `byte[]`** (Java object serialization
format) wrapping the actual PDF bytes.

**Binary format:**
```
Offset 0:  AC ED 00 05   - Java serialization magic + version 5
Offset 4:  75            - TC_ARRAY
Offset 5:  72 00 02 5B 42  - TC_CLASSDESC for "[B" (byte array)
Offset 10: AC F3 17 F8 06 08 54 E0  - serialVersionUID
Offset 18: 02 00 00      - classDescFlags + fields count
Offset 21: 78 70         - TC_ENDBLOCKDATA + TC_NULL
Offset 23: 4 bytes big-endian - actual PDF byte count (e.g. 00 00 37 1C = 14108)
Offset 27: <PDF bytes starting with %PDF-1.4>
```

**Extraction code:**
```python
import struct

def extract_pdf_from_java_bytes(raw: bytes) -> bytes:
    idx = raw.index(b'\x78\x70', 10)
    arr_len = struct.unpack('>I', raw[idx+2:idx+6])[0]
    return raw[idx+6:idx+6+arr_len]
```

**PDF content structure (iText 2.1.7):**
- Page 1: images (logos/form header) + disclosure body text
- Page 2: form fields + transaction table

The PDF encoding is **Windows-1252 / ISO-8859-9** (not UTF-8). Parse with pdfminer.six
using `codec='cp1252'` or rely on pdfminer's automatic detection.

**Sample extracted DKB PDF fields (SERVET NASIR / EGEPO context):**
```
SÜREKLİ BİLGİLERE İLİŞKİN ÖZEL DURUM AÇIKLAMASI
Konu: pay satış
Yapılan Açıklama Düzeltme mi?: HAYIR
Bildirime Konu Borsa Şirketi: NASMED ÖZEL SAĞLIK HİZMETLERİ TİCARET A.Ş.
Ad Soyad / Ticaret Ünvanı: SERVET NASIR
Tüzel Kişi Adına Bildirimi Yapanın Adı Soyadı: [empty]
Görevi: [empty]
Varsa Birlikte Hareket Eden Diğer Gerçek-Tüzel Kişiler: [empty]

Transaction table (25/05/2026):
  Buy nominal (TL):   0
  Sell nominal (TL):  2,500,000
  Net nominal (TL):  -2,500,000
  Start-of-day:       98,000,000 (19.6% capital, 22.25% voting)
  End-of-day:         95,500,000 (19.1% capital, 21.99% voting)
  Price range:        18.45 - 18.48 TL
```

---

### 3.4 BildirimPdf - `GET /en/api/BildirimPdf/{disclosureIndex}`

An alternative PDF endpoint that returns a KAP-generated summary PDF (iText 2.1.7).
This PDF is a **clean standard PDF** (not Java-wrapped) containing only the disclosure
narrative, **not** the full transaction table. Use `/tr/api/file/download/{objId}` instead.

---

### 3.5 Company List - `GET /tr/api/company/items/{memberType}/A`

Returns all active companies of a given type.

| memberType | Description |
|---|---|
| `IGS` | BIST-listed companies (HT member type) |
| `YK` | Investment firms |
| `PYS` | Portfolio management companies |
| `BDK` | Independent auditing firms |
| `DCS` | Rating agencies |

**Sample response element:**
```json
{
  "kapMemberOid": "33E5FED705EA00EAE0530A4A622B2AEA",
  "kapMemberType": "IGS",
  "kapMemberState": "A",
  "mkkMemberOid": "4028e4a2420327a4014209c55161144d",
  "kapMemberTitle": "ACIPAYAM SELÜLOZ SANAYİ VE TİCARET A.Ş.",
  "stockCode": "ACSEL",
  ...
}
```

**⚠️ Known issue (May 2026):** HT member-type endpoint (kap-client's `Kap.find_company()`)
returns empty list for BIST-listed tickers - use `IGS` type directly or use the
`members/byCriteria` endpoint with empty `mkkMemberOidList`.

---

## 4. Rate Limiting and Anti-Scraping Observations

- **No explicit `Retry-After` headers observed** in any response (200 returned for all calls)
- The KAP WAF has been observed to **drop TCP connections after ~6 seconds** for some request
  patterns (noted in `bist-trading-system/src/data/kap_scraper.py`)
- **Recommended default:** 2 req/s (0.5s between requests), configurable
- **Observed capacity:** The `byCriteria` POST returned in <2s for 7-day windows; no 429s
  observed during this reconnaissance
- **Session warmup:** A GET to `/tr/bildirim-sorgu` before API calls appears to help avoid
  WAF timeout (sets session cookies)
- **No pagination token in response:** If window returns 2000 results, narrow the date range

---

## 5. Turkish Locale Formatting

| Format | Example | Parsed as |
|---|---|---|
| Number (thousands separator `.`, decimal `,`) | `1.234.567,89` | `1234567.89` |
| Number with percent | `% 19,10` | `0.191` |
| Date `DD.MM.YYYY` | `26.05.2026` | `date(2026, 5, 26)` |
| Date `DD/MM/YYYY` | `25/05/2026` | `date(2026, 5, 25)` |
| DateTime `DD.MM.YYYY HH:MM:SS` | `26.05.2026 09:10:35` | `datetime(2026,5,26,9,10,35)` |

---

## 6. Key Identifiers

| Field | Source | Notes |
|---|---|---|
| `disclosureIndex` | list + detail API | Integer, sequential; use in URL paths |
| `disclosureId` | detail API `.disclosureBasic.disclosureId` | Hex UUID; stable; use as `kap_disclosure_id` |
| `mkkMemberOid` | detail API | Company OID for filter queries |
| `objId` | detail API `.attachments[].objId` | Attachment download key |

---

## 7. Correction / Amendment Logic

- `disclosureBasic.isChanged`: non-null string when this disclosure amends a previous one
- `disclosureBasic.relatedDisclosureOid`: hex OID of the original disclosure
- In the list API response: `modifyStatus` field is non-null for corrections
- Strategy: if `isChanged` is non-null → set `is_correction=True`, record `corrects_disclosure_id`

---

## 8. Pagination Note

The `byCriteria` endpoint caps responses at 2,000 records. For large backfills:

```python
# Example: 30-day backfill in 7-day windows
from datetime import date, timedelta

start = date(2026, 4, 28)
end   = date(2026, 5, 28)
window = timedelta(days=7)

cursor = start
while cursor < end:
    chunk_end = min(cursor + window, end)
    disclosures = fetch_disclosures(cursor.isoformat(), chunk_end.isoformat())
    process(disclosures)
    cursor = chunk_end + timedelta(days=1)
```

---

## 9. Fixture Files

| File | Index | Class | Description |
|---|---|---|---|
| `tests/fixtures/kap/sample_insider_disclosure.html` | 1611120 | ODA | PARDUS fund company threshold crossing - full structured HTML |
| `tests/fixtures/kap/sample_insider_disclosure_dkb.html` | 1611139 | DKB | KAP-relayed SPK II-15.1 individual insider - PDF attachment |

The ODA fixture has complete `tbl_oda-10400_Shares-Transaction-Notification` taxonomy table
and is used for parser unit tests.

---

## 11. Yönetim Kurulu (Management Board) Endpoint - TASK-005-B Recon

> **Reconnaissance date:** 2026-05-28

### Summary

No dedicated JSON API for board composition was found despite probing:
`/tr/api/company/executives/`, `/tr/api/company/boardMembers/`,
`/tr/api/company-detail/disclosures/YK/`, `/tr/api/sgbf/...` - all returned 404 or empty `[]`.

Board data is served as **server-rendered HTML** on the company "genel" page.

### Step 1 - Company OID / permaLink lookup

**URL:** `GET https://www.kap.org.tr/tr/api/member/filter/{ticker}`

**Response (KAPLM example):**
```json
{
  "companyCode": "993",
  "mkkMemberOid": "4028e4a1416e696501416f314a3960dc",
  "title": "KAPLAMİN AMBALAJ SANAYİ VE TİCARET A.Ş.",
  "permaLink": "993-kaplamin-ambalaj-sanayi-ve-ticaret-a-s"
}
```

### Step 2 - Management Board HTML page

**URL:** `GET https://www.kap.org.tr/tr/sirket-bilgileri/genel/{permaLink}`

**Response:** Server-rendered HTML. No `__NEXT_DATA__` JSON.

**Board table identification:** Find `<table>` whose `<thead>` contains a `<th>` with
text `"Bağımsız Yönetim Kurulu Üyesi Olup Olmadığı"`. This distinguishes the 17-column
board table from the 5-column executive table (which also starts with "Adı-Soyadı").

**CSS classes (observed 2026-05-28):**
- Table: `table-auto w-full text-left`
- Header row: `bg-light-gray rounded-xl company__sgbf-bold`
- `<th>`: `p-4 mb-3 text-sm font-semibold px-4 py-2`
- `<td>`: `p-4 mb-3 text-sm font-normal`

**Column layout (0-indexed, 17 columns total):**

| Index | Header | Used |
|-------|--------|------|
| 0 | Adı-Soyadı | full_name |
| 3 | Görevi | role |
| 5 | Yönetim Kuruluna İlk Seçilme Tarihi | valid_from (DD/MM/YYYY) |
| 12 | Bağımsız Yönetim Kurulu Üyesi Olup Olmadığı | is_independent |

**Independence values:**
- `"Bağımsız Üye"` → `is_independent=True`
- `"Bağımsız Üye Değil"` → `is_independent=False`

**Sample data - KAPLM (5 members):**

| Name | Role | Independent |
|------|------|-------------|
| RIZA KANDEMİR | Yönetim Kurulu Başkanı | No |
| ENVER GEÇGEL | Yönetim Kurulu Başkan Vekili | No |
| FERİDUN GEÇGEL | Yönetim Kurulu Üyesi | No |
| MUHAMMED DENİZ | Yönetim Kurulu Üyesi | **Yes** |
| BÜLENT AYHAN | Yönetim Kurulu Üyesi | **Yes** |

**Rate limit:** 2 req/s (same as other endpoints). No batch endpoint; 2 req/company.

---

## 10. Outstanding Unknowns / Future Work

1. **Relationship type parsing** (`Kendisi` / `Yakını` / `İlişkili Tüzel Kişi`): Present in
   the DKB PDF text when an insider is reporting on behalf of a related person or entity.
   When all three fields (`Tüzel Kişi Adına Bildirimi Yapanın Adı Soyadı`, `Görevi`,
   `Varsa Birlikte Hareket Eden...`) are empty → `Kendisi` (self). Regex matching needed.

2. **Price vs nominal value**: The PDF gives nominal TL value (face value × shares), not the
   market value. Share count = `nominal_TL / par_value` (par value is typically 1 TL for
   Turkish stocks). Price range is given separately as `X - Y TL` in the narrative text.

3. **Multi-row transactions**: Some disclosures have multiple transaction rows (different dates
   within the same notification period). The ODA HTML table supports multiple `new-type-row`
   tbody rows. The PDF may have multiple rows too.

4. **Backlog cap**: Testing revealed approximately 15-20 DKB insider disclosures per week.
   A 30-day backfill is expected to yield ~60-80 individual transaction disclosures.

---

# TSG Endpoint (TASK-007 Session 2 Recon)

**Source:** Türkiye Ticaret Sicili Gazetesi - TOBB (`https://www.ticaretsicil.gov.tr`)

## Access model

- **Free account + login required.** Login form (`FormUyeGirisi`) is CAPTCHA-gated.
- `robots.txt` → 404 (no explicit crawl restriction).
- **Saved session state does NOT survive** for `ilangoruntuleme.php` - restoring
  Playwright `storage_state` redirects to `girisyap.php`. Each scraper run must do a
  fresh interactive login (the only cookie set is a load-balancer cookie `atrsrv-*`;
  the real session is server-side and not portable).

## Two search surfaces

| Page | Field(s) | CAPTCHA | Use |
|------|----------|---------|-----|
| `unvansorgulama.php` | `UnvanSorgu` | yes | company-name → sicil no lookup (not used) |
| `ilangoruntuleme.php` | `TicaretUnvani` (≥5 chars) **or** `TicSicNo`, optional `SicilMudurluguId`, date range | yes | **primary** - lists gazette notices |

Search form id: `FormIlanGoruntuleme`. Submit via `form.requestSubmit()`; a CAPTCHA
appears on submission and must be solved by a human.

## Results table (`ilangoruntuleme.php`)

`tbody tr[role=row]`, columns:
`Müdürlük | Sicil No | Unvan | Yayın Tarihi | Sayı | Sayfa | İlan Türü | Gazete(PDF) | Sepet | Geri Bildirim`

PDF link in col 7: `pdf_goster.php?Guid={guid}`. One company → many notices
(e.g. Hera Teknik = 10 rows spanning 2019-2026), each its own gazette page.

## PDF retrieval (two-stage, CAPTCHA-gated)

1. Clicking a `pdf_goster.php?Guid=...` link opens a **popup** with a **second CAPTCHA**
   (`FormGuvenlikKodu` → AJAX `guvenlikkodudogrula.php`).
2. After the CAPTCHA, the real PDF is served from **`/tmp_gazete/{guid}.pdf`**.
   - This temp URL is **publicly fetchable without auth** once generated, but the guid is
     produced server-side post-CAPTCHA (≠ the `pdf_goster` guid), so it can't be predicted.
   - We capture the bytes via a Playwright route intercept on the popup.

## PDFs are SCANNED IMAGES - OCR required

- `%PDF-1.5`, but **zero text layer** (pdfminer/PyMuPDF text → empty; pages are `LTFigure`/image blocks).
- Pipeline: PyMuPDF render @300 DPI → Tesseract (`-l tur`) → text. Output is high quality
  (names, roles, TC kimlik, dates all legible). Requires Tesseract binary + `tur.traineddata`
  (system dependency, see README).

## Gazette page = MULTIPLE companies

A single gazette PDF page contains several companies' notices. Each notice starts with
`İlan Sıra No`, with the trade name on a line ending in `ANONİM ŞİRKETİ` / `LİMİTED ŞİRKETİ`.
**Parser must split into per-notice blocks and fuzzy-match the target company name** to pick
the correct block - never "first match" (would attribute the wrong company's directors).

Person/role pattern (post-OCR, whitespace-normalized):
`ikamet eden, AD SOYAD; DD.MM.YYYY tarihine kadar ROLE olarak seçilmiştir`
Roles seen: `Yönetim Kurulu Üyesi`, `Yönetim Kurulu Başkanı`, `Temsile Yetkili`,
`(YÖNETİM KURULU ÜYESİ) Temsile Yetkili`. "Temsile Yetkili" = authorized signatory → EXEC.

## Structural limit: NO reverse lookup → NO automatic BFS

The registry has no person→company search (confirmed across MERSİS/TSG/TOBB/e-Devlet).
Discovered director names cannot be turned into new company queries, so automatic BFS
graph expansion is impossible on this source. Expansion = manually feeding new seed
company names. `run_seed()` scrapes exactly the names given.

## Operating mode

Semi-automatic, headful Playwright: human logs in once and solves a CAPTCHA per search
and per PDF view; parsing, OCR, fuzzy matching and DB writes are automated.
