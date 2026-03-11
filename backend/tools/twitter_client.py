import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.config.settings import settings
from backend.models.harvester_output import TwitterData, TwitterQuote, TwitterSentimentScore

_TWITTER_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
_DEFAULT_MAX_RESULTS = 20
_MAX_RESULTS_LIMIT = 100


async def fetch_twitter(company_name: str, max_results: int = _DEFAULT_MAX_RESULTS) -> TwitterData:
    if not settings.twitter_bearer_token:
        return _empty_twitter_data()

    size = max(10, min(max_results, _MAX_RESULTS_LIMIT))
    payload = await asyncio.to_thread(_get_json, _build_search_url(company_name, size))

    tweets = payload.get("data")
    includes = payload.get("includes")
    if not isinstance(tweets, list) or not isinstance(includes, dict):
        return _empty_twitter_data()

    users = _users_by_id(includes.get("users"))
    verified_tweets = [tweet for tweet in tweets if _is_verified_tweet(tweet, users)]
    if not verified_tweets:
        return _empty_twitter_data()

    quotes = _extract_quotes(verified_tweets, users)
    sentiment = _sentiment_score([str(item.get("text") or "") for item in verified_tweets])
    return TwitterData(sentiment_score=sentiment, key_quotes=quotes)


def _build_search_url(company_name: str, max_results: int) -> str:
    params = {
        "query": f"{company_name} lang:en -is:retweet",
        "max_results": str(max_results),
        "expansions": "author_id",
        "tweet.fields": "created_at,lang,public_metrics,text",
        "user.fields": "name,username,verified",
    }
    return f"{_TWITTER_SEARCH_URL}?{urlencode(params)}"


def _get_json(url: str) -> dict[str, Any]:
    request = Request(
        url=url,
        headers={
            "Accept": "application/json",
            "User-Agent": settings.sec_edgar_user_agent,
            "Authorization": f"Bearer {settings.twitter_bearer_token}",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=settings.request_timeout_seconds) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Twitter transport failed: {exc}") from exc

    if isinstance(data, dict) and "errors" in data:
        message = json.dumps(data.get("errors"))
        raise RuntimeError(f"Twitter request failed: {message}")
    return data if isinstance(data, dict) else {}


def _users_by_id(raw_users: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_users, list):
        return {}
    output: dict[str, dict[str, Any]] = {}
    for user in raw_users:
        if not isinstance(user, dict):
            continue
        user_id = str(user.get("id") or "").strip()
        if not user_id:
            continue
        output[user_id] = user
    return output


def _is_verified_tweet(tweet: Any, users: dict[str, dict[str, Any]]) -> bool:
    if not isinstance(tweet, dict):
        return False
    author_id = str(tweet.get("author_id") or "").strip()
    if not author_id:
        return False
    user = users.get(author_id)
    if not isinstance(user, dict):
        return False
    return bool(user.get("verified"))


def _extract_quotes(tweets: list[dict[str, Any]], users: dict[str, dict[str, Any]]) -> list[TwitterQuote]:
    quotes: list[TwitterQuote] = []
    for tweet in tweets[:10]:
        author_id = str(tweet.get("author_id") or "").strip()
        user = users.get(author_id) or {}
        name = str(user.get("name") or "").strip()
        username = str(user.get("username") or "").strip()
        author = name or username or "unknown"
        role = "verified_account"
        text = str(tweet.get("text") or "").strip()
        if not text:
            continue
        tweet_id = str(tweet.get("id") or "").strip()
        url = f"https://x.com/{username}/status/{tweet_id}" if username and tweet_id else ""
        quotes.append(
            TwitterQuote(
                author=author,
                role=role,
                quote=text,
                date=_parse_datetime(tweet.get("created_at")),
                url=url,
            )
        )
    return quotes


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            return datetime.now(timezone.utc)
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _sentiment_score(texts: list[str]) -> TwitterSentimentScore:
    positive_terms = (
        "beat",
        "strong",
        "growth",
        "upside",
        "bullish",
        "outperform",
        "buy",
        "profit",
        "surge",
    )
    negative_terms = (
        "miss",
        "weak",
        "downside",
        "bearish",
        "sell",
        "loss",
        "drop",
        "risk",
        "decline",
    )
    positive = 0
    negative = 0
    neutral = 0
    for text in texts:
        lower = text.lower()
        pos_hits = sum(1 for term in positive_terms if term in lower)
        neg_hits = sum(1 for term in negative_terms if term in lower)
        if pos_hits > neg_hits:
            positive += 1
        elif neg_hits > pos_hits:
            negative += 1
        else:
            neutral += 1
    total = positive + negative + neutral
    if total == 0:
        return TwitterSentimentScore(positive=0.0, negative=0.0, neutral=1.0)
    return TwitterSentimentScore(
        positive=round(positive / total, 4),
        negative=round(negative / total, 4),
        neutral=round(neutral / total, 4),
    )


def _empty_twitter_data() -> TwitterData:
    return TwitterData(
        sentiment_score=TwitterSentimentScore(positive=0.0, negative=0.0, neutral=1.0),
        key_quotes=[],
    )
