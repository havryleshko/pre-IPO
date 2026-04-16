from __future__ import annotations

from typing import Any

import re

from backend.agents.prospectus_parser import (
    S1_DISCLOSURE_CHECKLIST_CUSTOMER_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_MARKET_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_PROFIT_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_PROJECTION_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_REVENUE_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_RISK_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_SPARSE_CLAIM_ID,
)
from backend.models.single_agent_result import ClaimCheck

_MAX_EXCERPT_LEN = 340
_PLACEHOLDER_BUSINESS_MODEL = frozenset(
    {
        "Business model summary not clearly stated in available filing text.",
        "Preliminary analysis. S-1 filing not available.",
    }
)


def _first_quote(check: ClaimCheck | None) -> str:
    if check is None or not check.evidence_quotes:
        return ""
    q = str(check.evidence_quotes[0] or "").strip()
    return q


def _check_map(disclosure_checks: list[ClaimCheck]) -> dict[str, ClaimCheck]:
    return {c.claim_id: c for c in disclosure_checks}


def _business_model_is_placeholder(business_model: str) -> bool:
    s = business_model.strip()
    return not s or s in _PLACEHOLDER_BUSINESS_MODEL


def _normalize_excerpt_lines(candidates: list[str], *, max_lines: int = 4) -> list[str]:
    kept: list[str] = []
    for raw in candidates:
        t = raw.strip()
        if not t:
            continue
        if len(t) > _MAX_EXCERPT_LEN:
            t = t[: _MAX_EXCERPT_LEN - 1].rstrip() + "…"
        tl = t.lower()
        drop_idx: list[int] = []
        skip_new = False
        for i, existing in enumerate(kept):
            el = existing.lower()
            if tl in el and len(t) <= len(existing):
                skip_new = True
                break
            if el in tl and len(existing) <= len(t):
                drop_idx.append(i)
        if skip_new:
            continue
        for i in reversed(drop_idx):
            kept.pop(i)
        kept.append(t)
    return kept[:max_lines]


def _append_unique(body: list[str], line: str) -> None:
    t = line.strip()
    if not t:
        return
    tl = t.lower()
    for e in body:
        el = e.lower()
        if tl == el or tl in el or el in tl:
            return
    body.append(t)


def _management_tone_label(
    *,
    by_id: dict[str, ClaimCheck],
    filing_excerpt_count: int,
    business_model: str,
) -> str:
    proj = by_id.get(S1_DISCLOSURE_CHECKLIST_PROJECTION_CLAIM_ID)
    if proj is not None and proj.status == "supported":
        return "SPAC-style projections"
    if filing_excerpt_count == 0 and _business_model_is_placeholder(business_model):
        return "vague"
    prof = by_id.get(S1_DISCLOSURE_CHECKLIST_PROFIT_CLAIM_ID)
    risk = by_id.get(S1_DISCLOSURE_CHECKLIST_RISK_CLAIM_ID)
    if (prof is not None and prof.status == "supported") or (risk is not None and risk.status == "supported"):
        return "conservative"
    rev = by_id.get(S1_DISCLOSURE_CHECKLIST_REVENUE_CLAIM_ID)
    mkt = by_id.get(S1_DISCLOSURE_CHECKLIST_MARKET_CLAIM_ID)
    if (rev is not None and rev.status == "supported") or (mkt is not None and mkt.status == "supported"):
        return "aggressive"
    return "conservative"


def _sparse_or_topic_line(
    *,
    by_id: dict[str, ClaimCheck],
    business_model: str,
) -> str:
    sparse = by_id.get(S1_DISCLOSURE_CHECKLIST_SPARSE_CLAIM_ID)
    if sparse is not None and sparse.status == "supported":
        return "No numeric guidance; narrative focused on lock-up and share count only."
    topic = ""
    if not _business_model_is_placeholder(business_model):
        topic = business_model.strip()[:80].rstrip()
    if not topic:
        topic = _first_quote(sparse)[:80].strip()
    if not topic:
        topic = "lock-up and offering structure"
    return f"No numeric guidance; narrative focused on {topic}."


def _roadshow_line(parser_output: dict[str, Any]) -> str:
    demand = parser_output.get("demand_signals")
    demand_dict = demand if isinstance(demand, dict) else {}
    roadshow = str(demand_dict.get("roadshow_sentiment") or "").strip()
    if roadshow and not roadshow.lower().startswith("no clear roadshow"):
        return roadshow[:220]
    inst = demand_dict.get("institutional_interest")
    if isinstance(inst, str) and inst.strip().lower() not in {"", "unknown"}:
        return f"Institutional interest: {inst.strip()}."
    return ""


_REVENUE_BASELINE_RE = re.compile(
    r"\b(?:revenue|net\s+revenue|total\s+revenue|tam|sam|som|market\s+size|cagr|compound\s+annual|burn|runway)\b",
    flags=re.IGNORECASE,
)
_PROFIT_BASELINE_RE = re.compile(
    r"\b(?:profitability|profitable|break[- ]?even|breakeven|positive\s+cash\s+flow)\b",
    flags=re.IGNORECASE,
)


def _pick_forecast_baselines(candidates: list[str]) -> list[str]:
    revenue_line = ""
    profit_line = ""
    for raw in candidates:
        line = raw.strip()
        if not line:
            continue
        if not revenue_line and _REVENUE_BASELINE_RE.search(line):
            revenue_line = line
        if not profit_line and _PROFIT_BASELINE_RE.search(line):
            profit_line = line
        if revenue_line and profit_line:
            break
    out: list[str] = []
    if revenue_line:
        out.append(revenue_line)
    if profit_line:
        out.append(profit_line)
    return out


def build_key_pre_ipo_claim_lines(
    parser_output: dict[str, Any],
    disclosure_checks: list[ClaimCheck],
    derived_fallback_lines: list[str],
) -> tuple[list[str], list[str]]:
    by_id = _check_map(disclosure_checks)
    business_model = str(parser_output.get("business_model") or "").strip()

    financials = parser_output.get("financials")
    financials_dict = financials if isinstance(financials, dict) else {}
    rev_evidence = financials_dict.get("revenue_evidence")
    rev_quote = ""
    if isinstance(rev_evidence, dict):
        rev_quote = str(rev_evidence.get("quote") or "").strip()

    ordered_candidates: list[str] = []
    if rev_quote:
        ordered_candidates.append(rev_quote)
    ordered_candidates.extend(
        [
            _first_quote(by_id.get(S1_DISCLOSURE_CHECKLIST_REVENUE_CLAIM_ID)),
            _first_quote(by_id.get(S1_DISCLOSURE_CHECKLIST_MARKET_CLAIM_ID)),
            _first_quote(by_id.get(S1_DISCLOSURE_CHECKLIST_PROFIT_CLAIM_ID)),
            _first_quote(by_id.get(S1_DISCLOSURE_CHECKLIST_CUSTOMER_CLAIM_ID)),
            _first_quote(by_id.get(S1_DISCLOSURE_CHECKLIST_RISK_CLAIM_ID)),
            business_model if not _business_model_is_placeholder(business_model) else "",
        ]
    )

    baselines = _pick_forecast_baselines(ordered_candidates)
    raw_candidates: list[str] = [*baselines, *ordered_candidates]

    filing_body = _normalize_excerpt_lines(raw_candidates, max_lines=4)
    filing_excerpt_count = len(filing_body)

    tone_label = _management_tone_label(
        by_id=by_id,
        filing_excerpt_count=filing_excerpt_count,
        business_model=business_model,
    )
    tone_line = f"Management tone: {tone_label}"

    body: list[str] = list(filing_body)

    if filing_excerpt_count < 2:
        _append_unique(body, _sparse_or_topic_line(by_id=by_id, business_model=business_model))

    if filing_excerpt_count < 2:
        rs = _roadshow_line(parser_output)
        if rs:
            _append_unique(body, rs)

    fallback_queue = list(derived_fallback_lines)
    while len(body) < 2 and fallback_queue:
        nxt = fallback_queue.pop(0).strip()
        if nxt:
            _append_unique(body, nxt)

    if len(body) < 2:
        body.append("No numeric guidance; narrative focused on lock-up and offering structure.")

    body = body[:6]

    source_excerpts = list(filing_body[:4])
    full_lines = [tone_line, *body]
    return full_lines, source_excerpts
