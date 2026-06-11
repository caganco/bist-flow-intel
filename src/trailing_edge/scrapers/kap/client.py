"""Low-level KAP HTTP client: warmup, list, detail, PDF download + unwrap."""
from datetime import date

from trailing_edge.core.config import get_config
from trailing_edge.core.http import RateLimitedClient
from trailing_edge.core.logging import get_logger

_log = get_logger(__name__)

_PDF_LEN_OFFSET = 23
_PDF_DATA_OFFSET = 27


def unwrap_java_pdf(raw: bytes) -> bytes:
    """Strip the Java-serialized byte[] wrapper and return raw PDF bytes."""
    length = int.from_bytes(raw[_PDF_LEN_OFFSET:_PDF_DATA_OFFSET], "big")
    return raw[_PDF_DATA_OFFSET: _PDF_DATA_OFFSET + length]


class KapClient:
    def __init__(self, http_client: RateLimitedClient) -> None:
        cfg = get_config()
        self._base = cfg["kap"]["base_url"].rstrip("/")
        self._endpoints = cfg["kap"]["endpoints"]
        self._filters = cfg["kap"]["filters"]
        self._http = http_client

    async def warmup(self) -> None:
        url = self._base + self._endpoints["warmup"]
        await self._http.get(url)
        _log.info("kap_warmup_done")

    async def fetch_disclosure_list(self, from_date: date, to_date: date) -> list[dict]:
        url = self._base + self._endpoints["list"]
        payload = {
            "fromDate": from_date.strftime("%Y-%m-%d"),
            "toDate": to_date.strftime("%Y-%m-%d"),
            "mkkMemberOidList": [],
            "subjectList": [],
        }
        resp = await self._http.post(url, json=payload)
        data: list[dict] = resp.json()
        target_subject = self._filters["target_subject"]
        target_class = self._filters["target_class"]
        filtered = [
            d for d in data
            if d.get("subject") == target_subject and d.get("disclosureClass") == target_class
        ]
        _log.info(
            "kap_list_fetched",
            total=len(data),
            filtered=len(filtered),
            from_date=str(from_date),
            to_date=str(to_date),
        )
        return filtered

    async def fetch_disclosure_detail(self, disclosure_index: str) -> dict:
        path = self._endpoints["detail"].format(disclosure_index=disclosure_index)
        url = self._base + path
        resp = await self._http.get(url)
        data = resp.json()
        # API returns a list with one element; unwrap it
        if isinstance(data, list):
            return data[0] if data else {}
        return data

    async def fetch_pdf(self, obj_id: str) -> bytes:
        path = self._endpoints["pdf"].format(obj_id=obj_id)
        url = self._base + path
        resp = await self._http.get(url)
        raw = resp.content
        pdf = unwrap_java_pdf(raw)
        _log.debug("pdf_unwrapped", obj_id=obj_id, raw_len=len(raw), pdf_len=len(pdf))
        return pdf
