"""Turkish timezone helpers and KAP date parsing."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

TR_TZ = ZoneInfo("Europe/Istanbul")

_DATE_FORMATS = ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d")
_DATETIME_FORMATS = (
    "%Y.%m.%d %H:%M:%S",   # detail API: "2026.05.26 09:10:35"
    "%d.%m.%Y %H:%M:%S",   # list API:   "26.05.2026 09:10:35"
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
)


def now_tr() -> datetime:
    return datetime.now(tz=TR_TZ)


def parse_kap_date(s: str) -> date:
    s = s.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse KAP date: {s!r}")


def parse_kap_datetime(s: str) -> datetime:
    s = s.strip()
    for fmt in _DATETIME_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=TR_TZ)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse KAP datetime: {s!r}")


def is_bist_trading_day(d: date) -> bool:
    return d.weekday() < 5  # Mon–Fri; no holiday calendar yet
