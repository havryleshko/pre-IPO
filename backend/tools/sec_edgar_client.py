import asyncio
from datetime import date, datetime
import json
import logging
from html.parser import HTMLParser
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode, urljoin
from xml.etree import ElementTree

from backend.config.settings import settings
from backend.models.harvester_output import SecFiling

_SEC_BROWSE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
_SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SEC_BASE_URL = "https://www.sec.gov"
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
_SUPPORTED_FORMS = ("S-1", "S-1/A", "F-1", "424B4")
_POST_IPO_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A")
_EXPLICIT_SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,5}(?:[.-][A-Z0-9]{1,4})?$")

_ISSUER_SUFFIX_STOPWORDS: frozenset[str] = frozenset(
    {
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
        "company",
        "ltd",
        "limited",
        "llc",
        "lp",
        "plc",
        "holdings",
        "holding",
        "group",
        "the",
    }
)

logger = logging.getLogger(__name__)


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


class _DocumentLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_row = False
        self._in_cell = False
        self._cell_index = -1
        self._current_href: str | None = None
        self._current_cells: list[str] = []
        self.rows: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "tr":
            self._in_row = True
            self._cell_index = -1
            self._current_href = None
            self._current_cells = []
            return
        if not self._in_row:
            return
        if tag in ("td", "th"):
            self._in_cell = True
            self._cell_index += 1
            self._current_cells.append("")
            return
        if tag == "a" and self._in_cell:
            href = attr_map.get("href", "").strip()
            if href:
                self._current_href = href

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th"):
            self._in_cell = False
            return
        if tag == "tr" and self._in_row:
            self._in_row = False
            if len(self._current_cells) >= 4 and self._current_href:
                self.rows.append(
                    {
                        "description": self._current_cells[1].strip(),
                        "document": self._current_cells[2].strip(),
                        "type": self._current_cells[3].strip(),
                        "href": self._current_href,
                    }
                )

    def handle_data(self, data: str) -> None:
        if not self._in_row or not self._in_cell or self._cell_index < 0:
            return
        text = data.strip()
        if not text:
            return
        current = self._current_cells[self._cell_index]
        self._current_cells[self._cell_index] = f"{current} {text}".strip()


async def fetch_sec_edgar(company_name: str, max_filings: int = 3) -> list[SecFiling]:
    cik = await asyncio.to_thread(_lookup_company_cik, company_name)
    if cik is None:
        return []

    issuer_name = await asyncio.to_thread(_resolve_conformed_issuer_name, cik)
    norm = company_name.strip().upper()
    input_is_direct_ticker = _is_explicit_symbol_query(norm) and _lookup_cik_from_ticker(norm) == cik
    if issuer_name and not input_is_direct_ticker:
        matches, score, requested_norm, issuer_norm = _issuer_name_match(company_name, issuer_name)
        if not matches:
            logger.warning(
                "SEC issuer mismatch requested=%r issuer=%r requested_norm=%r issuer_norm=%r score=%.3f cik=%s",
                company_name,
                issuer_name,
                requested_norm,
                issuer_norm,
                score,
                cik,
            )
            return []

    filing_sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for filing_type in ("S-1", "F-1", "424B4"):
        feed_root = await asyncio.to_thread(_fetch_feed, _build_browse_url(CIK=cik, type=filing_type, owner="exclude", count=max_filings, output="atom", action="getcompany"))
        for source in _extract_filing_sources(feed_root):
            filing_url = source.get("filing_url")
            if not filing_url or filing_url in seen_urls:
                continue
            seen_urls.add(filing_url)
            filing_sources.append(source)

    filings: list[SecFiling] = []
    for source in filing_sources[:max_filings]:
        filing_type = str(source.get("filing_type") or "")
        filing_url = source.get("filing_url")
        if not filing_url:
            continue

        source_url, raw_text = await asyncio.to_thread(_get_primary_filing_text, filing_url, filing_type)
        parsed_text = _normalize_text(raw_text)
        if not parsed_text:
            continue

        filings.append(
            SecFiling(
                url=source_url,
                text=parsed_text,
                filing_type=filing_type or "unknown",
            )
        )

    return filings


async def fetch_post_ipo_filings(ticker: str, ipo_date: date) -> str | None:
    return await asyncio.to_thread(_fetch_post_ipo_filings_sync, ticker, ipo_date)


async def resolve_ticker_from_name(company_name: str) -> str:
    return await asyncio.to_thread(_resolve_ticker_from_name_sync, company_name)


async def resolve_ticker_from_input(query: str) -> str:
    return await asyncio.to_thread(_resolve_ticker_from_input_sync, query)


def _fetch_post_ipo_filings_sync(ticker: str, ipo_date: date) -> str | None:
    cik = _lookup_cik_from_ticker(ticker)
    if cik is None:
        return None

    filing_sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for filing_type in ("10-K", "10-Q"):
        feed_root = _fetch_feed(
            _build_browse_url(
                CIK=cik,
                type=filing_type,
                owner="exclude",
                count=40,
                output="atom",
                action="getcompany",
            )
        )
        for source in _extract_post_ipo_filing_sources(feed_root, ipo_date):
            filing_url = source.get("filing_url")
            if not filing_url or filing_url in seen_urls:
                continue
            seen_urls.add(filing_url)
            filing_sources.append(source)

    filing_sources.sort(key=lambda item: (item.get("filing_date") or "", item.get("filing_type") or ""))
    for source in filing_sources:
        filing_type = str(source.get("filing_type") or "")
        if not filing_type.upper().startswith("10-K"):
            continue
        filing_url = source.get("filing_url")
        if not filing_url:
            continue
        _, raw_text = _get_primary_filing_text(filing_url, filing_type)
        parsed_text = _normalize_text(raw_text)
        if parsed_text:
            return parsed_text
    return None


def _resolve_ticker_from_name_sync(company_name: str) -> str:
    ticker_data = _fetch_json(_SEC_TICKERS_URL)
    normalized_query = _normalize_name(company_name)
    candidates = _extract_ticker_company_records(ticker_data)
    if not candidates:
        raise RuntimeError(f"SEC ticker lookup failed for {company_name!r}")

    ranked = sorted(
        candidates,
        key=lambda item: _company_match_score(normalized_query, _normalize_name(item["name"])),
        reverse=True,
    )
    best = ranked[0]
    if _company_match_score(normalized_query, _normalize_name(best["name"])) == (0, 0, 0):
        raise RuntimeError(f"No SEC ticker match found for {company_name!r}")

    issuer_name = _resolve_conformed_issuer_name(best["cik"])
    if issuer_name:
        matches, score, requested_norm, issuer_norm = _issuer_name_match(company_name, issuer_name)
        if not matches:
            raise RuntimeError(
                "SEC issuer mismatch requested=%r issuer=%r requested_norm=%r issuer_norm=%r score=%.3f"
                % (company_name, issuer_name, requested_norm, issuer_norm, score)
            )
    return best["ticker"]


def _resolve_ticker_from_input_sync(query: str) -> str:
    stripped = query.strip()
    if not stripped:
        return ""
    normalized = stripped.upper()
    if _is_explicit_symbol_query(normalized):
        return normalized
    return _resolve_ticker_from_name_sync(query)


def _lookup_company_cik(company_name: str) -> str | None:
    norm = company_name.strip().upper()
    if _is_explicit_symbol_query(norm):
        return _lookup_cik_from_ticker(norm)

    ticker_match = _lookup_company_cik_from_tickers(company_name)
    if ticker_match is not None:
        return ticker_match

    feed_root = _fetch_feed(
        _build_browse_url(
            action="getcompany",
            company=company_name,
            owner="exclude",
            count=10,
            output="atom",
        )
    )
    candidates = _extract_company_candidates(feed_root)
    if not candidates:
        return None
    normalized_query = _normalize_name(company_name)
    ranked = sorted(
        candidates,
        key=lambda item: _company_match_score(normalized_query, _normalize_name(item["name"])),
        reverse=True,
    )
    best = ranked[0]
    if _company_match_score(normalized_query, _normalize_name(best["name"])) == (0, 0, 0):
        return None
    return best["cik"]


def _lookup_company_cik_from_tickers(company_name: str) -> str | None:
    ticker_data = _fetch_json(_SEC_TICKERS_URL)
    normalized_query = _normalize_name(company_name)
    candidates = _extract_ticker_company_records(ticker_data)
    if not candidates:
        return None

    ranked = sorted(
        candidates,
        key=lambda item: _company_match_score(normalized_query, _normalize_name(item["name"])),
        reverse=True,
    )
    best = ranked[0]
    if _company_match_score(normalized_query, _normalize_name(best["name"])) == (0, 0, 0):
        return None
    return best["cik"]


def _is_explicit_symbol_query(normalized: str) -> bool:
    if not normalized:
        return False
    compact = normalized.replace(" ", "")
    if compact != normalized:
        return False
    return bool(_EXPLICIT_SYMBOL_RE.fullmatch(compact))


def _lookup_cik_from_ticker(ticker: str) -> str | None:
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        return None
    ticker_data = _fetch_json(_SEC_TICKERS_URL)
    for item in _extract_ticker_company_records(ticker_data):
        if item["ticker"] == normalized_ticker:
            return item["cik"]
    return None


def _extract_ticker_company_records(ticker_data: dict[str, Any]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for item in ticker_data.values():
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        ticker = str(item.get("ticker") or "").strip().upper()
        cik_value = item.get("cik_str")
        if not title or not ticker or cik_value is None:
            continue
        candidates.append(
            {
                "name": title,
                "ticker": ticker,
                "cik": str(cik_value).zfill(10),
            }
        )
    return candidates


def _fetch_feed(url: str) -> ElementTree.Element:
    request = Request(
        url=url,
        headers={
            "Accept": "application/atom+xml,text/xml,application/xml",
            "User-Agent": settings.sec_edgar_user_agent,
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=settings.request_timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return ElementTree.fromstring(body)
    except (HTTPError, URLError, TimeoutError, ElementTree.ParseError) as exc:
        raise RuntimeError(f"SEC EDGAR search failed: {exc}") from exc


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(
        url=url,
        headers={
            "Accept": "application/json",
            "User-Agent": settings.sec_edgar_user_agent,
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=settings.request_timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"SEC EDGAR lookup failed: {exc}") from exc


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


def _get_body(url: str) -> tuple[str, str]:
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
            return content_type, body
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"SEC filing fetch failed: {exc}") from exc


def _get_primary_filing_text(index_url: str, filing_type: str) -> tuple[str, str]:
    content_type, body = _get_body(index_url)
    primary_url = _resolve_primary_document_url(index_url, filing_type, body)
    if primary_url != index_url:
        return primary_url, _get_text(primary_url)
    if "html" in content_type or body.lstrip().startswith("<"):
        parser = _TextExtractor()
        parser.feed(body)
        return index_url, parser.get_text()
    return index_url, body


def _build_browse_url(**params: Any) -> str:
    query = urlencode(params)
    return f"{_SEC_BROWSE_URL}?{query}"


def _extract_company_candidates(root: ElementTree.Element) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        content = entry.find("atom:content", _ATOM_NS)
        if content is None:
            continue
        name = _child_text(content, "company-info/conformed-name")
        cik = _child_text(content, "company-info/cik")
        if name and cik:
            candidates.append({"name": name, "cik": cik})
    return candidates


def _resolve_conformed_issuer_name(cik: str) -> str | None:
    feed_root = _fetch_feed(
        _build_browse_url(
            action="getcompany",
            CIK=cik,
            owner="exclude",
            count=1,
            output="atom",
        )
    )
    candidates = _extract_company_candidates(feed_root)
    if not candidates:
        return None
    return candidates[0].get("name") or None


def _extract_filing_sources(root: ElementTree.Element) -> list[dict[str, str]]:
    filings: list[dict[str, str]] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        content = entry.find("atom:content", _ATOM_NS)
        if content is None:
            continue
        filing_type = _child_text(content, "filing-type")
        filing_url = _child_text(content, "filing-href")
        if filing_type in _SUPPORTED_FORMS and filing_url:
            filings.append({"filing_type": filing_type, "filing_url": filing_url})
    return filings


def _extract_post_ipo_filing_sources(root: ElementTree.Element, ipo_date: date) -> list[dict[str, str]]:
    filings: list[dict[str, str]] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        content = entry.find("atom:content", _ATOM_NS)
        if content is None:
            continue
        filing_type = str(_child_text(content, "filing-type") or "").upper()
        filing_url = _child_text(content, "filing-href")
        filing_date = _parse_filing_date(_child_text(content, "filing-date") or _child_text(entry, "updated"))
        if filing_type not in _POST_IPO_FORMS or not filing_url or filing_date is None:
            continue
        if filing_date <= ipo_date:
            continue
        filings.append(
            {
                "filing_type": filing_type,
                "filing_url": filing_url,
                "filing_date": filing_date.isoformat(),
            }
        )
    filings.sort(key=lambda item: (item["filing_date"], item["filing_type"]))
    return filings


def _resolve_primary_document_url(index_url: str, filing_type: str, index_html: str) -> str:
    parser = _DocumentLinkParser()
    parser.feed(index_html)
    filing_type_upper = filing_type.upper().strip()

    preferred = [
        row
        for row in parser.rows
        if row["href"]
        and row["href"].lower().endswith((".htm", ".html"))
        and row["type"].upper().strip() == filing_type_upper
    ]
    if preferred:
        return urljoin(index_url, preferred[0]["href"])

    fallback = [
        row
        for row in parser.rows
        if row["href"] and row["href"].lower().endswith((".htm", ".html"))
    ]
    if fallback:
        return urljoin(index_url, fallback[0]["href"])

    return index_url


def _child_text(node: ElementTree.Element, path: str) -> str | None:
    current: ElementTree.Element | None = node
    for part in path.split("/"):
        if current is None:
            return None
        current = current.find(f"atom:{part}", _ATOM_NS)
    if current is None or current.text is None:
        return None
    value = current.text.strip()
    return value or None


def _parse_filing_date(value: str | None) -> date | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    for parser in (date.fromisoformat, _parse_datetime_to_date):
        try:
            return parser(text)
        except ValueError:
            continue
    return None


def _parse_datetime_to_date(value: str) -> date:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized).date()


def _company_match_score(query: str, candidate: str) -> tuple[int, int, int]:
    if not query or not candidate:
        return (0, 0, 0)
    query_tokens = set(query.split())
    candidate_tokens = set(candidate.split())
    overlap = len(query_tokens & candidate_tokens)
    exact = int(query == candidate)
    contains = int(query in candidate)
    return (exact, contains, overlap)


def _normalize_name(value: str) -> str:
    lowered = value.lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(cleaned.split())

def _normalize_issuer_name(value: str) -> str:
    normalized = _normalize_name(value)
    if not normalized:
        return ""
    tokens = [t for t in normalized.split() if t and t not in _ISSUER_SUFFIX_STOPWORDS]
    return " ".join(tokens)


def _issuer_name_match(requested_company_name: str, issuer_name: str) -> tuple[bool, float, str, str]:
    requested_norm = _normalize_issuer_name(requested_company_name)
    issuer_norm = _normalize_issuer_name(issuer_name)
    if not requested_norm or not issuer_norm:
        return (False, 0.0, requested_norm, issuer_norm)

    if requested_norm == issuer_norm:
        return (True, 1.0, requested_norm, issuer_norm)

    requested_tokens = set(requested_norm.split())
    issuer_tokens = set(issuer_norm.split())
    if not requested_tokens or not issuer_tokens:
        return (False, 0.0, requested_norm, issuer_norm)

    overlap = requested_tokens & issuer_tokens
    jaccard = len(overlap) / max(1, len(requested_tokens | issuer_tokens))

    is_subset = requested_tokens.issubset(issuer_tokens) or issuer_tokens.issubset(requested_tokens)
    passes = is_subset and jaccard >= 0.6
    return (passes, float(jaccard), requested_norm, issuer_norm)


def _normalize_text(value: str) -> str:
    parts = value.split()
    return " ".join(parts)
