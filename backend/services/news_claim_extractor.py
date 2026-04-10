from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Literal

from backend.models.eval_case import ClaimType
from backend.models.single_agent_result import NewsDerivedClaim

logger = logging.getLogger(__name__)

_DOLLAR_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)\s*(billion|million)?", flags=re.IGNORECASE)
_UNIT_RE = re.compile(r"(?<!\$)(\d+(?:\.\d+)?)\s*(billion|million)", flags=re.IGNORECASE)
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|\bpercent\b)", flags=re.IGNORECASE)
_SHARE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(million)?\s*shares", flags=re.IGNORECASE)
_RANGE_RE = re.compile(r"\$(\d+(?:\.\d+)?)\s*(?:to|-|and)\s*\$(\d+(?:\.\d+)?)", flags=re.IGNORECASE)
_BILLION_RANGE_RE = re.compile(
    r"\$(\d+(?:\.\d+)?)\s*billion\s*(?:to|-|and)\s*\$?\s*(\d+(?:\.\d+)?)\s*billion",
    flags=re.IGNORECASE,
)
_RAISE_BILLION_RANGE_RE = re.compile(
    r"\$(\d+(?:\.\d+)?)\s*billion\s*(?:to|-|and)\s*\$?\s*(\d+(?:\.\d+)?)\s*billion",
    flags=re.IGNORECASE,
)
_SHARES_COMMA_RE = re.compile(r"(\d{1,3}(?:,\d{3})+)\s+shares", flags=re.IGNORECASE)
_NORTH_OF_BILLION_RE = re.compile(r"north of \$?\s*([\d,]+(?:\.\d+)?)\s*billion", flags=re.IGNORECASE)
_SINGLE_PRICE_RE = re.compile(
    r"\$(\d+(?:\.\d+)?)\s*(?:per share|apiece|each)\b",
    flags=re.IGNORECASE,
)
_IPO_PRICE_CTX_RE = re.compile(
    r"(?:ipo|offering|priced|share\s+price)[^$]{0,120}\$(\d+(?:\.\d+)?)\b",
    flags=re.IGNORECASE,
)
_AD_REV_RE = re.compile(
    r"(?:advertising|ad)\s+revenue\s+[^$\n]{0,120}\$\s*([\d,]+(?:\.\d+)?)\s*million",
    flags=re.IGNORECASE,
)
_NET_LOSS_RE = re.compile(
    r"net\s+loss[^$\n]{0,120}\$\s*([\d,]+(?:\.\d+)?)\s*million",
    flags=re.IGNORECASE,
)
_PAREN_LOSS_RE = re.compile(r"\$\(\s*([\d,]+(?:\.\d+)?)\s*\)\s*million", flags=re.IGNORECASE)


def _money_to_millions(raw: str, unit: str | None) -> float | None:
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None
    u = (unit or "").lower()
    if u == "billion":
        return value * 1000.0
    if u == "million":
        return value
    if value >= 1_000_000:
        return value / 1_000_000.0
    if value < 10:
        return None
    return value


def _money_mentions_in_millions(text: str) -> list[tuple[float, int, int]]:
    out: list[tuple[float, int, int]] = []
    for match in _DOLLAR_RE.finditer(text):
        v = _money_to_millions(match.group(1), match.group(2))
        if v is not None:
            out.append((v, match.start(), match.end()))
    for match in _UNIT_RE.finditer(text):
        v = _money_to_millions(match.group(1), match.group(2))
        if v is not None:
            out.append((v, match.start(), match.end()))
    return out


def _window(text: str, start: int, end: int, pad: int = 80) -> str:
    a = max(0, start - pad)
    b = min(len(text), end + pad)
    return text[a:b].strip()


def _article_source_kind(sources_active: list[str], article_source_name: str) -> Literal["news_api", "rss"]:
    an = article_source_name.lower()
    if "newsapi" in an or an == "news_api":
        return "news_api"
    if an == "rss":
        return "rss"
    if "news_api" in sources_active and "rss_feeds" not in sources_active:
        return "news_api"
    if "rss_feeds" in sources_active and "news_api" not in sources_active:
        return "rss"
    return "news_api"


def _coerce_article_dict(a: dict[str, Any], idx: int) -> tuple[str, str, str, datetime | None]:
    title = str(a.get("title") or "").strip()
    content = str(a.get("content") or "").strip()
    url = str(a.get("url") or f"article_{idx}").strip()
    published: datetime | None = None
    raw_date = a.get("date")
    if isinstance(raw_date, datetime):
        published = raw_date
    elif isinstance(raw_date, str) and raw_date.strip():
        try:
            published = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except ValueError:
            published = None
    return title, content, url, published


def _append_claim(
    out: list[NewsDerivedClaim],
    seen: set[tuple[str, str, float | None]],
    *,
    claim_id: str,
    claim_type: ClaimType,
    normalized_value: float | None,
    units: str | None,
    period: str | None,
    source: Literal["news_api", "rss"],
    evidence_quote: str,
    article_url: str,
    published_at: datetime | None,
) -> None:
    key = (article_url, claim_type, round(normalized_value, 4) if normalized_value is not None else None)
    if key in seen:
        return
    seen.add(key)
    out.append(
        NewsDerivedClaim(
            claim_id=claim_id,
            claim_type=claim_type,
            normalized_value=normalized_value,
            units=units,
            period=period,
            source=source,
            evidence_quote=evidence_quote[:500],
            article_url=article_url,
            published_at=published_at,
        )
    )


def _growth_from_nearby_amounts(text: str) -> list[tuple[float, int, int]]:
    results: list[tuple[float, int, int]] = []
    lower = text.lower()
    if "doubled" in lower:
        vals = sorted({v for v, _, _ in _money_mentions_in_millions(text) if v >= 50.0})
        if len(vals) >= 2:
            lo, hi = vals[-2], vals[-1]
            if lo > 0:
                pct = round((hi - lo) / lo * 100.0, 4)
                pos = lower.find("doubled")
                results.append((pct, pos, pos + 6))
    pair = re.search(
        r"\$\s*([\d,]+(?:\.\d+)?)\s*million.*?\$\s*([\d,]+(?:\.\d+)?)\s*million",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if pair:
        try:
            a = float(pair.group(1).replace(",", ""))
            b = float(pair.group(2).replace(",", ""))
            older, newer = min(a, b), max(a, b)
            if older > 0 and ("growth" in lower or "rise" in lower or "%" in text):
                pct = round((newer - older) / older * 100.0, 4)
                results.append((pct, pair.start(), pair.end()))
        except ValueError:
            pass
    return results


def extract_news_derived_claims(harvester_output: dict[str, Any]) -> list[NewsDerivedClaim]:
    articles_raw = harvester_output.get("news_articles")
    if not isinstance(articles_raw, list):
        logger.info("news_claim_extractor: no news_articles list")
        return []

    sources_active = harvester_output.get("sources_active")
    active_list = sources_active if isinstance(sources_active, list) else []
    active_norm = [str(x).strip() for x in active_list if isinstance(x, str)]

    out: list[NewsDerivedClaim] = []
    seen: set[tuple[str, str, float | None]] = set()
    seq = 0

    for idx, raw in enumerate(articles_raw):
        if not isinstance(raw, dict):
            continue
        article_source = str(raw.get("source") or "").strip()
        src_kind = _article_source_kind(active_norm, article_source)
        title, content, url, published = _coerce_article_dict(raw, idx)
        full = f"{title}\n{content}".strip()
        if not full:
            continue

        lower = full.lower()

        for pct, s, e in _growth_from_nearby_amounts(full):
            seq += 1
            _append_claim(
                out,
                seen,
                claim_id=f"nc_{idx}_growth_{seq}",
                claim_type="growth_rate",
                normalized_value=pct,
                units="percent",
                period=None,
                source=src_kind,
                evidence_quote=_window(full, s, e),
                article_url=url,
                published_at=published,
            )

        for m in _PCT_RE.finditer(full):
            ctx = full[max(0, m.start() - 60) : m.end() + 60].lower()
            if not any(
                k in ctx
                for k in (
                    "growth",
                    "rise",
                    "increase",
                    "revenue",
                    "sales",
                    "yoy",
                    "year",
                    "versus",
                    "from",
                    "fell",
                    "decline",
                )
            ):
                continue
            seq += 1
            val = float(m.group(1))
            pre = full[max(0, m.start() - 50) : m.start()].lower()
            if any(w in pre for w in ("fell", "decline", "drop", "down", "negative")):
                val = -abs(val)
            _append_claim(
                out,
                seen,
                claim_id=f"nc_{idx}_growth_pct_{seq}",
                claim_type="growth_rate",
                normalized_value=val,
                units="percent",
                period=None,
                source=src_kind,
                evidence_quote=_window(full, m.start(), m.end()),
                article_url=url,
                published_at=published,
            )

        for val, s, e in _money_mentions_in_millions(full):
            ctx = full[max(0, s - 120) : min(len(full), e + 120)].lower()
            if not any(
                k in ctx
                for k in (
                    "revenue",
                    "sales",
                    "posted",
                    "growing",
                    "growth",
                    "from",
                    "fiscal",
                    "year",
                    "delivered",
                )
            ):
                continue
            seq += 1
            ad_adj = "ad revenue" in ctx or "advertising revenue" in ctx
            _append_claim(
                out,
                seen,
                claim_id=f"nc_{idx}_{'adrev' if ad_adj else 'revenue'}_{seq}",
                claim_type="ad_revenue" if ad_adj else "revenue",
                normalized_value=round(val, 4),
                units="usd_millions",
                period=None,
                source=src_kind,
                evidence_quote=_window(full, s, e),
                article_url=url,
                published_at=published,
            )

        for m in _AD_REV_RE.finditer(full):
            try:
                v = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            seq += 1
            _append_claim(
                out,
                seen,
                claim_id=f"nc_{idx}_adrev_{seq}",
                claim_type="ad_revenue",
                normalized_value=round(v, 4),
                units="usd_millions",
                period=None,
                source=src_kind,
                evidence_quote=_window(full, m.start(), m.end()),
                article_url=url,
                published_at=published,
            )

        for m in _NET_LOSS_RE.finditer(full):
            try:
                v = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            seq += 1
            _append_claim(
                out,
                seen,
                claim_id=f"nc_{idx}_netloss_{seq}",
                claim_type="net_loss",
                normalized_value=round(v, 4),
                units="usd_millions",
                period=None,
                source=src_kind,
                evidence_quote=_window(full, m.start(), m.end()),
                article_url=url,
                published_at=published,
            )

        m_loss = _PAREN_LOSS_RE.search(full)
        if m_loss and "loss" in lower:
            try:
                v = float(m_loss.group(1).replace(",", ""))
            except ValueError:
                pass
            else:
                seq += 1
                _append_claim(
                    out,
                    seen,
                    claim_id=f"nc_{idx}_netloss_paren_{seq}",
                    claim_type="net_loss",
                    normalized_value=round(v, 4),
                    units="usd_millions",
                    period=None,
                    source=src_kind,
                    evidence_quote=_window(full, m_loss.start(), m_loss.end()),
                    article_url=url,
                    published_at=published,
                )

        for m_uv in re.finditer(
            r"(?:up to|at least|about|around)\s+\$?\s*([\d,]+(?:\.\d+)?)\s*billion",
            full,
            flags=re.IGNORECASE,
        ):
            try:
                bil = float(m_uv.group(1).replace(",", ""))
            except ValueError:
                continue
            seq += 1
            _append_claim(
                out,
                seen,
                claim_id=f"nc_{idx}_val_upto_{seq}",
                claim_type="valuation",
                normalized_value=round(bil, 4),
                units="usd_billions",
                period=None,
                source=src_kind,
                evidence_quote=_window(full, m_uv.start(), m_uv.end()),
                article_url=url,
                published_at=published,
            )
        for m_ve in re.finditer(
            r"valuation[^$\n]{0,80}\$([\d,]+(?:\.\d+)?)\s*billion",
            full,
            flags=re.IGNORECASE,
        ):
            span_end = min(len(full), m_ve.end() + 40)
            if "between" in full[m_ve.start() : span_end].lower():
                continue
            try:
                bil = float(m_ve.group(1).replace(",", ""))
            except ValueError:
                continue
            seq += 1
            _append_claim(
                out,
                seen,
                claim_id=f"nc_{idx}_val_phrase_{seq}",
                claim_type="valuation",
                normalized_value=round(bil, 4),
                units="usd_billions",
                period=None,
                source=src_kind,
                evidence_quote=_window(full, m_ve.start(), m_ve.end()),
                article_url=url,
                published_at=published,
            )
        m_no = _NORTH_OF_BILLION_RE.search(full)
        if m_no:
            try:
                bil = float(m_no.group(1).replace(",", ""))
            except ValueError:
                bil = None
            if bil is not None:
                seq += 1
                _append_claim(
                    out,
                    seen,
                    claim_id=f"nc_{idx}_val_north_{seq}",
                    claim_type="valuation",
                    normalized_value=round(bil, 4),
                    units="usd_billions",
                    period=None,
                    source=src_kind,
                    evidence_quote=_window(full, m_no.start(), m_no.end()),
                    article_url=url,
                    published_at=published,
                )

        m_br = _BILLION_RANGE_RE.search(full)
        if m_br:
            mid = (float(m_br.group(1)) + float(m_br.group(2))) / 2.0
            seq += 1
            _append_claim(
                out,
                seen,
                claim_id=f"nc_{idx}_val_range_{seq}",
                claim_type="valuation",
                normalized_value=round(mid, 4),
                units="usd_billions",
                period=None,
                source=src_kind,
                evidence_quote=_window(full, m_br.start(), m_br.end()),
                article_url=url,
                published_at=published,
            )

        for m_rm in re.finditer(
            r"(?:raise|raising|to raise)[^$\n]{0,100}\$\s*([\d,]+(?:\.\d+)?)\s*million",
            full,
            flags=re.IGNORECASE,
        ):
            try:
                pm = float(m_rm.group(1).replace(",", ""))
            except ValueError:
                continue
            seq += 1
            _append_claim(
                out,
                seen,
                claim_id=f"nc_{idx}_proceeds_m_{seq}",
                claim_type="proceeds",
                normalized_value=round(pm, 4),
                units="usd_millions",
                period=None,
                source=src_kind,
                evidence_quote=_window(full, m_rm.start(), m_rm.end()),
                article_url=url,
                published_at=published,
            )
        m_raise = _RAISE_BILLION_RANGE_RE.search(full)
        if m_raise:
            low = float(m_raise.group(1)) * 1000.0
            high = float(m_raise.group(2)) * 1000.0
            mid_m = (low + high) / 2.0
            ctx = full[max(0, m_raise.start() - 40) : m_raise.end() + 40].lower()
            if any(k in ctx for k in ("raise", "raising", "ipo", "offering", "priced")):
                seq += 1
                _append_claim(
                    out,
                    seen,
                    claim_id=f"nc_{idx}_proceeds_{seq}",
                    claim_type="proceeds",
                    normalized_value=round(mid_m, 4),
                    units="usd_millions",
                    period=None,
                    source=src_kind,
                    evidence_quote=_window(full, m_raise.start(), m_raise.end()),
                    article_url=url,
                    published_at=published,
                )

        m_sc = _SHARES_COMMA_RE.search(full)
        if m_sc:
            try:
                sh = float(m_sc.group(1).replace(",", "")) / 1_000_000.0
            except ValueError:
                sh = None
            if sh is not None:
                seq += 1
                _append_claim(
                    out,
                    seen,
                    claim_id=f"nc_{idx}_shares_comma_{seq}",
                    claim_type="share_count",
                    normalized_value=round(sh, 4),
                    units="millions_of_shares",
                    period=None,
                    source=src_kind,
                    evidence_quote=_window(full, m_sc.start(), m_sc.end()),
                    article_url=url,
                    published_at=published,
                )

        m_sh = _SHARE_RE.search(full)
        if m_sh:
            value = float(m_sh.group(1))
            if (m_sh.group(2) or "").lower() == "million":
                sh_m = value
            else:
                sh_m = value / 1_000_000.0
            seq += 1
            _append_claim(
                out,
                seen,
                claim_id=f"nc_{idx}_shares_{seq}",
                claim_type="share_count",
                normalized_value=round(sh_m, 4),
                units="millions_of_shares",
                period=None,
                source=src_kind,
                evidence_quote=_window(full, m_sh.start(), m_sh.end()),
                article_url=url,
                published_at=published,
            )

        m_rg = _RANGE_RE.search(full)
        if m_rg:
            mid = (float(m_rg.group(1)) + float(m_rg.group(2))) / 2.0
            seq += 1
            _append_claim(
                out,
                seen,
                claim_id=f"nc_{idx}_price_range_{seq}",
                claim_type="offering_price_range",
                normalized_value=round(mid, 4),
                units="usd_per_share",
                period=None,
                source=src_kind,
                evidence_quote=_window(full, m_rg.start(), m_rg.end()),
                article_url=url,
                published_at=published,
            )

        for m_sp in _SINGLE_PRICE_RE.finditer(full):
            seq += 1
            _append_claim(
                out,
                seen,
                claim_id=f"nc_{idx}_price_single_{seq}",
                claim_type="offering_price_range",
                normalized_value=round(float(m_sp.group(1)), 4),
                units="usd_per_share",
                period=None,
                source=src_kind,
                evidence_quote=_window(full, m_sp.start(), m_sp.end()),
                article_url=url,
                published_at=published,
            )
        m_ipo = _IPO_PRICE_CTX_RE.search(full)
        if m_ipo:
            seq += 1
            _append_claim(
                out,
                seen,
                claim_id=f"nc_{idx}_price_ipoctx_{seq}",
                claim_type="offering_price_range",
                normalized_value=round(float(m_ipo.group(1)), 4),
                units="usd_per_share",
                period=None,
                source=src_kind,
                evidence_quote=_window(full, m_ipo.start(), m_ipo.end()),
                article_url=url,
                published_at=published,
            )

    logger.info("news_claim_extractor: extracted %d claims from %d articles", len(out), len(articles_raw))
    return out
