import asyncio
import logging
import re
from datetime import date, datetime, timedelta, timezone
import importlib
from statistics import median
from typing import Any

_log = logging.getLogger(__name__)
_MIN_PLAUSIBLE_IPO_DATE = date(1980, 1, 1)
_EXPLICIT_SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,5}(?:[.-][A-Z0-9]{1,4})?$")
_IPO_DATE_RESOLUTION_ATTEMPTS = 3
_IPO_DATE_RESOLUTION_RETRY_BASE_SECONDS = 0.25


def _normalize_symbol_for_yahoo_fetch(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if normalized.endswith(".ASX"):
        return f"{normalized[:-4]}.AX"
    return normalized


def _yahoo_explicit_symbol_try_order(compact: str) -> list[str]:
    ordered: list[str] = [compact]
    mapped = _normalize_symbol_for_yahoo_fetch(compact)
    if mapped != compact and mapped not in ordered:
        ordered.append(mapped)
    return ordered


def _is_plausible_ipo_date(d: date) -> bool:
    return d >= _MIN_PLAUSIBLE_IPO_DATE

from backend.models.harvester_output import YahooFinanceData

_MAX_PEERS = 8


async def fetch_yahoo_finance(company_name: str) -> YahooFinanceData:
    return await asyncio.to_thread(_fetch_sync, company_name)


async def fetch_ipo_price_history(ticker: str, ipo_date: date) -> dict[str, Any]:
    return await asyncio.to_thread(_fetch_ipo_price_history_sync, ticker, ipo_date)


async def resolve_ipo_date_for_ticker(ticker: str) -> date | None:
    normalized = _normalize_symbol_for_yahoo_fetch(ticker)
    if not normalized:
        return None
    for attempt in range(1, _IPO_DATE_RESOLUTION_ATTEMPTS + 1):
        resolved = await asyncio.to_thread(_resolve_ipo_date_for_ticker_sync, normalized)
        if resolved is not None:
            return resolved
        if attempt < _IPO_DATE_RESOLUTION_ATTEMPTS:
            await asyncio.sleep(_IPO_DATE_RESOLUTION_RETRY_BASE_SECONDS * attempt)
    _log.warning(
        "Unable to resolve IPO date for ticker=%s after %s attempts",
        normalized,
        _IPO_DATE_RESOLUTION_ATTEMPTS,
    )
    return None


def _resolve_ipo_date_for_ticker_sync(ticker: str) -> date | None:
    normalized = _normalize_symbol_for_yahoo_fetch(ticker)
    if not normalized:
        return None
    try:
        yf = importlib.import_module("yfinance")
    except ImportError:
        return None
    info = _safe_info(yf, normalized)
    ipo_raw = info.get("ipoDate")
    if isinstance(ipo_raw, str) and ipo_raw.strip():
        try:
            candidate = date.fromisoformat(ipo_raw.strip()[:10])
            if _is_plausible_ipo_date(candidate):
                return candidate
        except ValueError:
            pass
    if isinstance(ipo_raw, (int, float)):
        try:
            candidate = datetime.fromtimestamp(int(ipo_raw), tz=timezone.utc).date()
            if _is_plausible_ipo_date(candidate):
                return candidate
        except (ValueError, OSError):
            pass
    epoch = info.get("firstTradeDateEpochUtc")
    if isinstance(epoch, (int, float)):
        try:
            candidate = datetime.fromtimestamp(int(epoch), tz=timezone.utc).date()
            if _is_plausible_ipo_date(candidate):
                return candidate
        except (ValueError, OSError):
            pass
    try:
        history = yf.Ticker(normalized).history(period="max")
    except Exception:
        return None
    if history is None or getattr(history, "empty", True):
        return None
    first_idx = history.index[0]
    try:
        if isinstance(first_idx, datetime):
            candidate = first_idx.date()
        else:
            to_py = getattr(first_idx, "to_pydatetime", None)
            if callable(to_py):
                dt = to_py()
                candidate = dt.date() if isinstance(dt, datetime) else None
            else:
                candidate = None
        if candidate is not None and _is_plausible_ipo_date(candidate):
            return candidate
    except Exception:
        pass
    return None


def _fetch_sync(company_name: str) -> YahooFinanceData:
    try:
        yf = importlib.import_module("yfinance")
    except ImportError:
        return YahooFinanceData()

    symbol = _resolve_symbol(yf, company_name)
    if not symbol:
        return YahooFinanceData()

    base_info = _safe_info(yf, symbol)
    sector = str(base_info.get("sector") or "").strip()
    industry = str(base_info.get("industry") or "").strip()
    country = str(base_info.get("country") or "").strip()
    exchange = str(base_info.get("exchange") or "").strip() or str(base_info.get("fullExchangeName") or "").strip()

    comparable_tickers = _resolve_comparables(yf, company_name, symbol, sector.lower(), industry.lower())
    sector_multiples = _collect_sector_multiples(yf, comparable_tickers) if comparable_tickers else {}
    sector_performance = _sector_90d_performance(yf, comparable_tickers) if comparable_tickers else None

    return YahooFinanceData(
        listing_ticker=symbol,
        sector=sector or None,
        industry=industry or None,
        country=country or None,
        exchange=exchange or None,
        comparable_companies=comparable_tickers,
        sector_multiples=sector_multiples,
        sector_90d_performance=sector_performance,
    )


def _close_points_for_ipo_window(yf: Any, normalized_ticker: str, ipo_date: date) -> list[tuple[date, float]]:
    try:
        history = yf.Ticker(normalized_ticker).history(start=ipo_date.isoformat(), auto_adjust=False)
    except Exception:
        history = None
    close_points = _extract_close_points(history) if history is not None else []
    if close_points:
        return close_points
    try:
        history_max = yf.Ticker(normalized_ticker).history(period="max", auto_adjust=False)
    except Exception:
        return []
    pts_max = _extract_close_points(history_max)
    if not pts_max:
        return []
    filtered = [p for p in pts_max if p[0] >= ipo_date]
    if filtered:
        if len(filtered) < len(pts_max):
            _log.info(
                "ipo_price_history: start= window empty for %s; using %s bars from max history on/after ipo_date=%s",
                normalized_ticker,
                len(filtered),
                ipo_date,
            )
        return filtered
    _log.warning(
        "ipo_price_history: ipo_date=%s is after first Yahoo bar %s for %s; using full max history for outcome metrics",
        ipo_date,
        pts_max[0][0],
        normalized_ticker,
    )
    return pts_max


def _fetch_ipo_price_history_sync(ticker: str, ipo_date: date) -> dict[str, Any]:
    lock_up_cliff_date = ipo_date + timedelta(days=180)
    empty_result = {
        "ipo_price": None,
        "current_price": None,
        "peak_price": None,
        "peak_date": None,
        "trough_price": None,
        "trough_date": None,
        "performance_since_ipo_pct": None,
        "lock_up_cliff_date": lock_up_cliff_date,
        "price_at_lock_up_cliff": None,
        "recovered_to_ipo_date": None,
        "recovered_to_peak_date": None,
    }

    normalized_ticker = _normalize_symbol_for_yahoo_fetch(ticker)
    if not normalized_ticker:
        return empty_result

    try:
        yf = importlib.import_module("yfinance")
    except ImportError:
        return empty_result

    close_points = _close_points_for_ipo_window(yf, normalized_ticker, ipo_date)
    if not close_points:
        return empty_result

    prices = [price for _, price in close_points]
    ipo_price = prices[0]
    if ipo_price <= 0:
        _log.warning("Non-positive IPO price %.4f for %s — skipping", ipo_price, normalized_ticker)
        return empty_result
    current_price = prices[-1]
    peak_price = max(prices)
    trough_price = min(prices)
    peak_date = _first_date_for_price(close_points, peak_price)
    trough_date = _first_date_for_price(close_points, trough_price)
    price_at_lock_up_cliff = _first_price_on_or_after(close_points, lock_up_cliff_date)
    recovered_to_ipo_date = _first_recovery_date(close_points[1:], ipo_price)
    recovered_to_peak_date = _first_recovery_date(close_points, peak_price)

    return {
        "ipo_price": round(ipo_price, 4),
        "current_price": round(current_price, 4),
        "peak_price": round(peak_price, 4),
        "peak_date": peak_date,
        "trough_price": round(trough_price, 4),
        "trough_date": trough_date,
        "performance_since_ipo_pct": _calculate_performance_pct(ipo_price, current_price),
        "lock_up_cliff_date": lock_up_cliff_date,
        "price_at_lock_up_cliff": round(price_at_lock_up_cliff, 4) if price_at_lock_up_cliff is not None else None,
        "recovered_to_ipo_date": recovered_to_ipo_date,
        "recovered_to_peak_date": recovered_to_peak_date,
    }


def _yahoo_info_resolves_symbol(info: dict[str, Any], symbol: str) -> bool:
    if not info:
        return False
    qt = str(info.get("quoteType") or "").strip().upper()
    if qt == "NONE":
        return False
    sym = str(info.get("symbol") or "").strip().upper()
    if sym and sym == symbol:
        return True
    if sym and sym.replace("-", ".") == symbol.replace("-", "."):
        return True
    return bool(
        qt in ("EQUITY", "ETF", "MUTUALFUND")
        or info.get("shortName")
        or info.get("longName")
    )


def _resolve_symbol(yf: Any, company_name: str) -> str:
    raw = company_name.strip()
    if not raw:
        return ""

    compact = raw.upper().replace(" ", "")
    if bool(_EXPLICIT_SYMBOL_RE.fullmatch(compact)):
        for cand in _yahoo_explicit_symbol_try_order(compact):
            info = _safe_info(yf, cand)
            if _yahoo_info_resolves_symbol(info, cand):
                return cand

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


def _extract_close_points(history: Any) -> list[tuple[date, float]]:
    try:
        close = history["Close"].dropna()
        index = close.index
        values = close.values
    except Exception:
        return []

    points: list[tuple[date, float]] = []
    for raw_index, raw_value in zip(index, values):
        point_date = _coerce_history_date(raw_index)
        point_value = _to_float(raw_value)
        if point_date is None or point_value is None:
            continue
        points.append((point_date, point_value))
    points.sort(key=lambda item: item[0])
    return points


def _coerce_history_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    to_pydatetime = getattr(value, "to_pydatetime", None)
    if callable(to_pydatetime):
        converted = to_pydatetime()
        if isinstance(converted, datetime):
            return converted.date()
        if isinstance(converted, date):
            return converted
    as_date = getattr(value, "date", None)
    if callable(as_date):
        converted = as_date()
        if isinstance(converted, date):
            return converted
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text)
        except ValueError:
            try:
                normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
                return datetime.fromisoformat(normalized).date()
            except ValueError:
                return None
    return None


def _first_price_on_or_after(points: list[tuple[date, float]], threshold: date) -> float | None:
    for point_date, point_value in points:
        if point_date >= threshold:
            return point_value
    return None


def _first_date_for_price(points: list[tuple[date, float]], target_price: float) -> date | None:
    for point_date, point_value in points:
        if abs(point_value - target_price) <= 1e-9:
            return point_date
    return None


def _first_recovery_date(points: list[tuple[date, float]], threshold_price: float) -> date | None:
    for point_date, point_value in points:
        if point_value >= threshold_price:
            return point_date
    return None


def _calculate_performance_pct(first: float, last: float) -> float | None:
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
