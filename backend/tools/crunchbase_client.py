import asyncio
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from backend.config.settings import settings
from backend.models.harvester_output import CrunchbaseData

_CRUNCHBASE_ENTITY_URL = "https://api.crunchbase.com/api/v4/entities/organizations"


async def fetch_crunchbase(company_name: str) -> CrunchbaseData:
    if not settings.crunchbase_api_key:
        return CrunchbaseData()

    payload = await asyncio.to_thread(_get_json, _build_lookup_url(company_name))
    return _to_crunchbase_data(payload)


def _build_lookup_url(company_name: str) -> str:
    identifier = quote(company_name.strip().lower().replace(" ", "-"), safe="")
    return f"{_CRUNCHBASE_ENTITY_URL}/{identifier}"


def _get_json(url: str) -> dict[str, Any]:
    request = Request(
        url=url,
        headers={
            "Accept": "application/json",
            "User-Agent": settings.sec_edgar_user_agent,
            "X-cb-user-key": settings.crunchbase_api_key or "",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=settings.request_timeout_seconds) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Crunchbase transport failed: {exc}") from exc

    if isinstance(data, dict) and data.get("status") in ("error", "ERROR"):
        message = str(data.get("message") or "unknown error")
        raise RuntimeError(f"Crunchbase request failed: {message}")
    return data if isinstance(data, dict) else {}


def _to_crunchbase_data(payload: dict[str, Any]) -> CrunchbaseData:
    properties = _extract_properties(payload)
    rounds = _extract_rounds(payload)
    investors = _extract_investors(payload, rounds)
    total_raised = _to_float(
        properties.get("funding_total")
        or properties.get("total_funding_usd")
        or properties.get("funding_total_usd")
    )
    last_valuation = _extract_last_valuation(payload, rounds)
    return CrunchbaseData(
        total_raised=total_raised,
        funding_rounds=rounds,
        investors=investors,
        last_valuation=last_valuation,
    )


def _extract_properties(payload: dict[str, Any]) -> dict[str, Any]:
    entities = payload.get("entities")
    if isinstance(entities, list) and entities:
        entity = entities[0]
        if isinstance(entity, dict):
            props = entity.get("properties")
            if isinstance(props, dict):
                return props
    if isinstance(payload.get("properties"), dict):
        return payload["properties"]
    if isinstance(payload.get("entity"), dict):
        entity = payload["entity"]
        if isinstance(entity.get("properties"), dict):
            return entity["properties"]
    return {}


def _extract_rounds(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = []
    cards = payload.get("cards")
    if isinstance(cards, dict):
        candidates.extend(
            [
                cards.get("funding_rounds"),
                cards.get("raised_funding_rounds"),
                cards.get("raised_investments"),
            ]
        )
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        items = candidate.get("items")
        if not isinstance(items, list):
            continue
        rounds: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            rounds.append(
                {
                    "round": str(item.get("funding_type") or item.get("identifier", {}).get("value") or "unknown"),
                    "amount": _to_float(item.get("money_raised") or item.get("money_raised_usd")),
                    "date": _extract_date(item),
                    "investors": _extract_round_investors(item),
                    "valuation": _to_float(item.get("post_money_valuation") or item.get("valuation")),
                }
            )
        return rounds
    return []


def _extract_investors(payload: dict[str, Any], rounds: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    cards = payload.get("cards")
    if isinstance(cards, dict):
        for card_name in ("investors", "raised_investments", "participated_funds"):
            card = cards.get(card_name)
            if not isinstance(card, dict):
                continue
            items = card.get("items")
            if not isinstance(items, list):
                continue
            for item in items:
                name = _investor_name(item)
                if not name or name in seen:
                    continue
                seen.add(name)
                ordered.append(name)
    for round_item in rounds:
        investors = round_item.get("investors")
        if not isinstance(investors, list):
            continue
        for investor in investors:
            name = str(investor).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            ordered.append(name)
    return ordered


def _extract_round_investors(item: dict[str, Any]) -> list[str]:
    names: list[str] = []
    investors = item.get("investors")
    if isinstance(investors, list):
        for investor in investors:
            name = _investor_name(investor)
            if name:
                names.append(name)
    lead = item.get("lead_investors")
    if isinstance(lead, list):
        for investor in lead:
            name = _investor_name(investor)
            if name:
                names.append(name)
    seen: set[str] = set()
    deduped: list[str] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped


def _investor_name(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    identifier = item.get("identifier")
    if isinstance(identifier, dict):
        value = identifier.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    name = item.get("name")
    if isinstance(name, str):
        return name.strip()
    return ""


def _extract_last_valuation(payload: dict[str, Any], rounds: list[dict[str, Any]]) -> float | None:
    properties = _extract_properties(payload)
    direct = _to_float(
        properties.get("valuation")
        or properties.get("valuation_usd")
        or properties.get("last_valuation")
        or properties.get("last_valuation_usd")
    )
    if direct is not None:
        return direct
    for round_item in reversed(rounds):
        value = _to_float(round_item.get("valuation"))
        if value is not None:
            return value
    return None


def _extract_date(item: dict[str, Any]) -> str | None:
    for key in ("announced_on", "closed_on", "date"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            raw = value.get("value")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    if isinstance(value, dict):
        for key in ("value_usd", "usd", "value", "amount"):
            parsed = _to_float(value.get(key))
            if parsed is not None:
                return parsed
    return None
