import asyncio
import json
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.config.settings import settings
from backend.models.harvester_output import SecFiling

_SEC_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
_SEC_BASE_URL = "https://www.sec.gov"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self._chunks.append(stripped)

    def get_text(self) -> str:
        return " ".join(self._chunks)


async def fetch_sec_edgar(company_name: str, max_filings: int = 3) -> list[SecFiling]:
    search_payload = {
        "q": company_name,
        "category": "custom",
        "forms": ["S-1", "S-1/A", "F-1", "424B4"],
        "startdt": "",
        "enddt": "",
        "from": 0,
        "size": max_filings,
        "sort": [{"filedAt": {"order": "desc"}}],
    }

    search_data = await asyncio.to_thread(_post_json, _SEC_SEARCH_URL, search_payload)
    hits = ((search_data.get("hits") or {}).get("hits") or [])

    filings: list[SecFiling] = []
    for hit in hits:
        source = hit.get("_source") or {}
        filing_type = str(source.get("form") or "")
        filing_url = _extract_filing_url(source)
        if not filing_url:
            continue

        raw_text = await asyncio.to_thread(_get_text, filing_url)
        parsed_text = _normalize_text(raw_text)
        if not parsed_text:
            continue

        filings.append(
            SecFiling(
                url=filing_url,
                text=parsed_text,
                filing_type=filing_type or "unknown",
            )
        )

    return filings


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": settings.sec_edgar_user_agent,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=settings.request_timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"SEC EDGAR search failed: {exc}") from exc


def _get_text(url: str) -> str:
    request = Request(
        url=url,
        headers={
            "Accept": "text/html,application/xml,text/plain,*/*",
            "User-Agent": settings.sec_edgar_user_agent,
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=settings.request_timeout_seconds) as response:
            content_type = str(response.headers.get("Content-Type", "")).lower()
            body = response.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"SEC filing fetch failed: {exc}") from exc

    if "html" in content_type or body.lstrip().startswith("<"):
        parser = _TextExtractor()
        parser.feed(body)
        return parser.get_text()

    return body


def _extract_filing_url(source: dict[str, Any]) -> str | None:
    for key in ("linkToTxt", "linkToHtml", "linkToFilingDetails"):
        value = source.get(key)
        if isinstance(value, str) and value:
            return value if value.startswith("http") else f"{_SEC_BASE_URL}{value}"

    adsh = source.get("adsh")
    ciks = source.get("ciks") or []
    if isinstance(adsh, str) and ciks:
        cik = str(ciks[0]).lstrip("0")
        accession = adsh.replace("-", "")
        path = f"/Archives/edgar/data/{cik}/{accession}/{adsh}-index.html"
        return f"{_SEC_BASE_URL}{path}"

    return None


def _normalize_text(value: str) -> str:
    parts = value.split()
    return " ".join(parts)
