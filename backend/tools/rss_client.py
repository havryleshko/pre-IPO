import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from backend.config.settings import settings
from backend.models.harvester_output import NewsArticle

logger = logging.getLogger(__name__)

_DEFAULT_RSS_TEMPLATES: tuple[str, ...] = (
    "https://news.google.com/rss/search?q={query}",
    "https://www.bing.com/news/search?q={query}&format=rss",
)


async def fetch_rss_feeds(
    company_name: str,
    days_back: int = 30,
    max_articles: int = 25,
    feed_templates: tuple[str, ...] = _DEFAULT_RSS_TEMPLATES,
) -> list[NewsArticle]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    query = quote_plus(company_name)
    feed_urls = [template.format(query=query) for template in feed_templates]

    parse_tasks = [asyncio.to_thread(_fetch_and_parse_feed, url) for url in feed_urls]
    raw_results = await asyncio.gather(*parse_tasks, return_exceptions=True)

    articles: list[NewsArticle] = []
    for feed_url, result in zip(feed_urls, raw_results):
        if isinstance(result, Exception):
            logger.warning("RSS fetch failed for %s: %s", feed_url, result)
            continue

        for entry in result:
            published = _coerce_datetime(entry.get("date"))
            if published is None or published < cutoff:
                continue

            title = str(entry.get("title") or "").strip()
            url = str(entry.get("url") or "").strip()
            content = str(entry.get("content") or "").strip()
            source = str(entry.get("source") or "rss").strip()
            if not title or not url:
                continue

            articles.append(
                NewsArticle(
                    source=source,
                    title=title,
                    date=published,
                    content=content,
                    url=url,
                    is_primary_source=False,
                )
            )

    articles.sort(key=lambda item: item.date, reverse=True)
    deduped: list[NewsArticle] = []
    seen_urls: set[str] = set()
    for article in articles:
        if article.url in seen_urls:
            continue
        seen_urls.add(article.url)
        deduped.append(article)
        if len(deduped) >= max_articles:
            break

    return deduped


def _fetch_and_parse_feed(url: str) -> list[dict[str, Any]]:
    request = Request(
        url=url,
        headers={
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9",
            "User-Agent": settings.sec_edgar_user_agent,
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=settings.request_timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"RSS request failed for {url}: {exc}") from exc

    return _parse_feed_xml(body)


def _parse_feed_xml(xml_text: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RuntimeError(f"RSS parse failed: {exc}") from exc

    entries: list[dict[str, Any]] = []
    for item in _iter_rss_items(root):
        title = _first_text(item, ("title",))
        link = _first_text(item, ("link",))
        description = _first_text(item, ("description", "summary", "content"))
        pub_date = _first_text(item, ("pubDate", "published", "updated"))
        source = _first_text(item, ("source",))
        entries.append(
            {
                "title": title or "",
                "url": link or "",
                "content": description or "",
                "date": pub_date,
                "source": source or "rss",
            }
        )

    if entries:
        return entries

    for item in _iter_atom_entries(root):
        title = _first_text(item, ("title",))
        link = _extract_atom_link(item)
        content = _first_text(item, ("content", "summary"))
        pub_date = _first_text(item, ("published", "updated"))
        source = _first_text(item, ("source", "author", "name"))
        entries.append(
            {
                "title": title or "",
                "url": link or "",
                "content": content or "",
                "date": pub_date,
                "source": source or "rss",
            }
        )

    return entries


def _iter_rss_items(root: ET.Element) -> list[ET.Element]:
    items: list[ET.Element] = []
    for element in root.iter():
        if _local_name(element.tag) == "item":
            items.append(element)
    return items


def _iter_atom_entries(root: ET.Element) -> list[ET.Element]:
    entries: list[ET.Element] = []
    for element in root.iter():
        if _local_name(element.tag) == "entry":
            entries.append(element)
    return entries


def _extract_atom_link(entry: ET.Element) -> str:
    for child in entry:
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if href:
            return href.strip()
        if child.text:
            return child.text.strip()
    return ""


def _first_text(element: ET.Element, names: tuple[str, ...]) -> str | None:
    for child in element.iter():
        if _local_name(child.tag) not in names:
            continue
        if child.text and child.text.strip():
            return child.text.strip()
    return None


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _coerce_datetime(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        value = raw
    else:
        text = str(raw).strip()
        if not text:
            return None
        parsed = _try_parse_datetime(text)
        if parsed is None:
            return None
        value = parsed

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _try_parse_datetime(value: str) -> datetime | None:
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        pass

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
