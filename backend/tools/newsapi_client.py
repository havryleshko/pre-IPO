import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.config.settings import settings
from backend.models.harvester_output import NewsArticle

_NEWSAPI_URL = "https://newsapi.org/v2/everything"
_NEWSAPI_MAX_PAGE_SIZE = 100


async def fetch_news_api(
    company_name: str,
    days_back: int = 30,
    max_articles: int = 20,
) -> list[NewsArticle]:
    if not settings.newsapi_api_key:
        return []

    size = max(1, min(max_articles, _NEWSAPI_MAX_PAGE_SIZE))
    requested_from_date = datetime.now(timezone.utc) - timedelta(days=days_back)
    effective_from_date = requested_from_date

    for _ in range(3):
        params = {
            "q": company_name,
            "from": effective_from_date.date().isoformat(),
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": str(size),
            "page": "1",
        }
        query = urlencode(params)
        try:
            payload = await asyncio.to_thread(_get_json, f"{_NEWSAPI_URL}?{query}")
            break
        except RuntimeError as exc:
            if "too far in the past" not in str(exc):
                raise
            effective_from_date = effective_from_date + timedelta(days=1)
    else:
        raise RuntimeError("NewsAPI request failed: requested window exceeds plan retention limit")

    status = str(payload.get("status") or "")
    if status != "ok":
        message = str(payload.get("message") or "unknown error")
        raise RuntimeError(f"NewsAPI request failed: {message}")

    raw_articles = payload.get("articles")
    if not isinstance(raw_articles, list):
        return []

    result: list[NewsArticle] = []
    for item in raw_articles:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        content = str(item.get("description") or item.get("content") or "").strip()
        source_data = item.get("source")
        if isinstance(source_data, dict):
            source = str(source_data.get("name") or "newsapi").strip()
        else:
            source = "newsapi"
        published_at = _parse_datetime(item.get("publishedAt"))
        if not title or not url or published_at is None:
            continue
        if published_at < effective_from_date:
            continue

        result.append(
            NewsArticle(
                source=source or "newsapi",
                title=title,
                date=published_at,
                content=content,
                url=url,
                is_primary_source=False,
            )
        )
        if len(result) >= size:
            break

    return result


def _get_json(url: str) -> dict[str, Any]:
    request = Request(
        url=url,
        headers={
            "Accept": "application/json",
            "User-Agent": settings.sec_edgar_user_agent,
            "X-Api-Key": settings.newsapi_api_key or "",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=settings.request_timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
            payload = json.loads(body)
            message = str(payload.get("message") or exc)
        except (OSError, json.JSONDecodeError):
            message = str(exc)
        raise RuntimeError(f"NewsAPI transport failed: {message}") from exc
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"NewsAPI transport failed: {exc}") from exc


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
