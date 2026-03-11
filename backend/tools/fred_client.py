import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.config.settings import settings
from backend.models.harvester_output import FredData

_FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
_FRED_SERIES_ID = "FEDFUNDS"
_CACHE: dict[str, Any] = {"value": None, "expires_at": None}


async def fetch_fred_data() -> FredData:
    cached = _get_cached()
    if cached is not None:
        return cached

    if not settings.fred_api_key:
        value = FredData()
        _set_cache(value)
        return value

    payload = await asyncio.to_thread(_get_json, _build_observations_url())
    value = _to_fred_data(payload)
    _set_cache(value)
    return value


def _build_observations_url() -> str:
    params = {
        "series_id": _FRED_SERIES_ID,
        "api_key": settings.fred_api_key or "",
        "file_type": "json",
        "sort_order": "desc",
        "limit": "2",
    }
    return f"{_FRED_OBSERVATIONS_URL}?{urlencode(params)}"


def _get_json(url: str) -> dict[str, Any]:
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
            data = json.loads(body)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"FRED transport failed: {exc}") from exc

    if isinstance(data, dict) and "error_message" in data:
        raise RuntimeError(f"FRED request failed: {data['error_message']}")
    return data if isinstance(data, dict) else {}


def _to_fred_data(payload: dict[str, Any]) -> FredData:
    observations = payload.get("observations")
    if not isinstance(observations, list) or not observations:
        return FredData(
            fed_funds_rate=None,
            market_conditions="unknown",
            retrieved_at=datetime.now(timezone.utc),
        )

    latest = _observation_value(observations[0])
    prior = _observation_value(observations[1]) if len(observations) > 1 else None
    conditions = _market_conditions(latest, prior)

    return FredData(
        fed_funds_rate=latest,
        market_conditions=conditions,
        retrieved_at=datetime.now(timezone.utc),
    )


def _observation_value(observation: Any) -> float | None:
    if not isinstance(observation, dict):
        return None
    value = observation.get("value")
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text == ".":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _market_conditions(latest: float | None, prior: float | None) -> str:
    if latest is None:
        return "unknown"
    if prior is None:
        if latest >= 5.0:
            return "restrictive"
        if latest >= 2.5:
            return "neutral"
        return "accommodative"
    delta = latest - prior
    if latest >= 5.0 and delta >= 0:
        return "restrictive and tightening"
    if latest >= 5.0 and delta < 0:
        return "restrictive but easing"
    if latest < 2.5 and delta <= 0:
        return "accommodative and easing"
    if delta > 0:
        return "tightening"
    if delta < 0:
        return "easing"
    return "stable"


def _get_cached() -> FredData | None:
    now = datetime.now(timezone.utc)
    expires_at = _CACHE.get("expires_at")
    value = _CACHE.get("value")
    if isinstance(expires_at, datetime) and expires_at > now and isinstance(value, FredData):
        return value
    return None


def _set_cache(value: FredData) -> None:
    now = datetime.now(timezone.utc)
    _CACHE["value"] = value
    _CACHE["expires_at"] = now + timedelta(hours=settings.source_cache_ttl_hours)
