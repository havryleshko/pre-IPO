import asyncio
import importlib
from statistics import median
from typing import Any

from backend.models.harvester_output import YahooFinanceData

_MAX_PEERS = 8


async def fetch_yahoo_finance(company_name: str) -> YahooFinanceData:
    return await asyncio.to_thread(_fetch_sync, company_name)


def _fetch_sync(company_name: str) -> YahooFinanceData:
    try:
        yf = importlib.import_module("yfinance")
    except ImportError:
        return YahooFinanceData()

    symbol = _resolve_symbol(yf, company_name)
    if not symbol:
        return YahooFinanceData()

    base_info = _safe_info(yf, symbol)
    sector = str(base_info.get("sector") or "").strip().lower()
    industry = str(base_info.get("industry") or "").strip().lower()

    comparable_tickers = _resolve_comparables(yf, company_name, symbol, sector, industry)
    if not comparable_tickers:
        return YahooFinanceData()
    sector_multiples = _collect_sector_multiples(yf, comparable_tickers)
    sector_performance = _sector_90d_performance(yf, comparable_tickers)

    return YahooFinanceData(
        comparable_companies=comparable_tickers,
        sector_multiples=sector_multiples,
        sector_90d_performance=sector_performance,
    )


def _resolve_symbol(yf: Any, company_name: str) -> str:
    raw = company_name.strip()
    if not raw:
        return ""

    direct = raw.upper().replace(" ", "")
    if 1 <= len(direct) <= 5 and direct.isalpha():
        return direct

    try:
        search = yf.Search(query=raw, max_results=5)
        quotes = getattr(search, "quotes", None)
    except Exception:
        quotes = None

    if isinstance(quotes, list):
        for quote in quotes:
            if not isinstance(quote, dict):
                continue
            symbol = str(quote.get("symbol") or "").strip().upper()
            quote_type = str(quote.get("quoteType") or "").upper()
            if symbol and quote_type in ("EQUITY", "MUTUALFUND", ""):
                return symbol
    return ""


def _safe_info(yf: Any, symbol: str) -> dict[str, Any]:
    try:
        data = yf.Ticker(symbol).info
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_comparables(yf: Any, company_name: str, symbol: str, sector: str, industry: str) -> list[str]:
    seen: set[str] = {symbol}
    candidates: list[str] = []
    for query in _peer_queries(company_name, sector, industry):
        for peer_symbol in _search_equities(yf, query):
            if peer_symbol in seen:
                continue
            seen.add(peer_symbol)
            candidates.append(peer_symbol)
            if len(candidates) >= _MAX_PEERS:
                return candidates
    return candidates


def _peer_queries(company_name: str, sector: str, industry: str) -> list[str]:
    queries: list[str] = []
    raw_name = company_name.strip()
    if raw_name:
        queries.append(raw_name)
    if industry:
        queries.append(f"{industry} stocks")
        queries.append(industry)
    if sector:
        queries.append(f"{sector} stocks")
        queries.append(sector)
    return queries


def _search_equities(yf: Any, query: str) -> list[str]:
    try:
        search = yf.Search(query=query, max_results=20)
        quotes = getattr(search, "quotes", None)
    except Exception:
        return []
    if not isinstance(quotes, list):
        return []
    symbols: list[str] = []
    for quote in quotes:
        if not isinstance(quote, dict):
            continue
        symbol = str(quote.get("symbol") or "").strip().upper()
        quote_type = str(quote.get("quoteType") or "").upper()
        if not symbol:
            continue
        if quote_type and quote_type != "EQUITY":
            continue
        symbols.append(symbol)
    return symbols


def _collect_sector_multiples(yf: Any, tickers: list[str]) -> dict[str, Any]:
    pe_values: list[float] = []
    forward_pe_values: list[float] = []
    ps_values: list[float] = []
    pb_values: list[float] = []

    for ticker in tickers:
        info = _safe_info(yf, ticker)
        trailing_pe = _to_float(info.get("trailingPE"))
        forward_pe = _to_float(info.get("forwardPE"))
        price_to_sales = _to_float(info.get("priceToSalesTrailing12Months"))
        price_to_book = _to_float(info.get("priceToBook"))
        if trailing_pe is not None:
            pe_values.append(trailing_pe)
        if forward_pe is not None:
            forward_pe_values.append(forward_pe)
        if price_to_sales is not None:
            ps_values.append(price_to_sales)
        if price_to_book is not None:
            pb_values.append(price_to_book)

    return {
        "trailing_pe_median": _median_or_none(pe_values),
        "forward_pe_median": _median_or_none(forward_pe_values),
        "price_to_sales_median": _median_or_none(ps_values),
        "price_to_book_median": _median_or_none(pb_values),
    }


def _sector_90d_performance(yf: Any, tickers: list[str]) -> float | None:
    performances: list[float] = []
    for ticker in tickers:
        perf = _ticker_90d_performance(yf, ticker)
        if perf is not None:
            performances.append(perf)
    if not performances:
        return None
    return round(sum(performances) / len(performances), 4)


def _ticker_90d_performance(yf: Any, ticker: str) -> float | None:
    try:
        history = yf.Ticker(ticker).history(period="3mo")
    except Exception:
        return None
    try:
        close = history["Close"].dropna()
        if len(close) < 2:
            return None
        first = float(close.iloc[0])
        last = float(close.iloc[-1])
    except Exception:
        return None
    if first <= 0:
        return None
    return round(((last - first) / first) * 100.0, 4)


def _median_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(median(values)), 4)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None
