from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.models.single_agent_result import (
    ClaimCheck,
    CompanyProfile,
    OutcomeMetrics,
    PatternClassification,
    PreIpoThesis,
    PredictionClaim,
    RealizedOutcome,
    ReferenceTableRow,
)

_REFERENCE_FILES = ("table-2.csv", "table-3.csv", "table-4.csv")
_PATTERN_RE = re.compile(r"pattern\s+(\d+)\s*:\s*(.+)", re.IGNORECASE)
_COMPANY_RE = re.compile(r"^(?P<name>.+?)(?:\s+\((?P<ticker>[^)]+)\))?$")
_TICKER_TOKEN_RE = re.compile(r"\b([A-Za-z]{1,5})\b")
_WORD_RE = re.compile(r"[a-z0-9]+")


class CanonicalReferenceRecord(BaseModel):
    company_name: str
    ticker: str | None = None
    company_ticker: str
    industry_region: str
    ipo_date: str
    key_pre_ipo_claims: str
    long_term_outcome: str
    forecast_error: str
    predicted_pattern: str
    predicted_pattern_id: int | None = None
    source_tables: list[str] = Field(default_factory=list)
    ambiguous_patterns: list[str] = Field(default_factory=list)


class OutputContractBundle(BaseModel):
    company_profile: CompanyProfile
    pre_ipo_thesis: PreIpoThesis
    realized_outcome: RealizedOutcome
    pattern_classification: PatternClassification
    reference_table_row: ReferenceTableRow


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _reference_dir() -> Path:
    return _repo_root() / "tests" / "evals" / "data"


def _normalize_company_key(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip()).lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _parse_company_ticker(value: str) -> tuple[str, str | None]:
    text = value.strip()
    match = _COMPANY_RE.match(text)
    if not match:
        return text, None
    name = re.sub(r"\s+", " ", (match.group("name") or text).strip())
    ticker_raw = match.group("ticker")
    if not ticker_raw:
        return name, None
    first_segment = ticker_raw.split(";", 1)[0].split(",", 1)[0].strip()
    token_matches = _TICKER_TOKEN_RE.findall(first_segment)
    if token_matches:
        return name, token_matches[-1].upper()
    return name, first_segment or None


def _pattern_parts(value: str) -> tuple[int | None, str]:
    text = re.sub(r"\s+", " ", value.strip())
    match = _PATTERN_RE.match(text)
    if not match:
        return None, text
    return int(match.group(1)), text


def _field_priority(source_table: str) -> int:
    order = {"table-2.csv": 1, "table-3.csv": 2, "table-4.csv": 3}
    return order.get(source_table, 0)


def _pick_canonical_value(values: list[tuple[str, str]]) -> str:
    if not values:
        return ""
    counts = Counter(text for text, _ in values if text)
    if not counts:
        return ""
    best_count = max(counts.values())
    candidates = {text for text, count in counts.items() if count == best_count}
    ranked = sorted(
        values,
        key=lambda item: (_field_priority(item[1]), len(item[0])),
        reverse=True,
    )
    for text, _source in ranked:
        if text in candidates:
            return text
    return ranked[0][0]


def _industry_tokens(text: str) -> set[str]:
    return {word for word in _WORD_RE.findall(text.lower()) if len(word) > 2}


def _safe_iso_date(value: date | None) -> str:
    return value.isoformat() if value is not None else "unavailable"


def outcome_metrics_has_core_price_signal(outcome_metrics: OutcomeMetrics | None) -> bool:
    if outcome_metrics is None:
        return False
    return any(
        value is not None
        for value in (
            outcome_metrics.ipo_price,
            outcome_metrics.current_price,
            outcome_metrics.peak_price,
            outcome_metrics.trough_price,
            outcome_metrics.performance_since_ipo_pct,
        )
    )


def format_long_term_outcome_line(
    *,
    company_name: str,
    outcome_metrics: OutcomeMetrics | None,
    delivery_verdict: str | None = None,
) -> str:
    return _derived_long_term_outcome(
        company_name=company_name,
        outcome_metrics=outcome_metrics,
        delivery_verdict=delivery_verdict,
    )


def _resolved_long_term_outcome_line(
    *,
    company_name: str,
    outcome_metrics: OutcomeMetrics | None,
    delivery_verdict: str | None,
    fallback_line: str | None = None,
) -> str:
    if outcome_metrics_has_core_price_signal(outcome_metrics):
        return format_long_term_outcome_line(
            company_name=company_name,
            outcome_metrics=outcome_metrics,
            delivery_verdict=delivery_verdict,
        )
    fallback = str(fallback_line or "").strip()
    if fallback:
        return fallback
    return _derived_long_term_outcome(
        company_name=company_name,
        outcome_metrics=outcome_metrics,
        delivery_verdict=delivery_verdict,
    )


@lru_cache(maxsize=1)
def load_canonical_reference_dataset() -> list[CanonicalReferenceRecord]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    base_dir = _reference_dir()
    for filename in _REFERENCE_FILES:
        path = base_dir / filename
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                company_ticker = str(row.get("Company (Ticker)") or "").strip()
                if not company_ticker:
                    continue
                company_name, ticker = _parse_company_ticker(company_ticker)
                key = ticker.upper() if ticker else _normalize_company_key(company_name)
                grouped[key].append(
                    {
                        "company_name": company_name,
                        "ticker": ticker.upper() if ticker else None,
                        "company_ticker": company_ticker,
                        "industry_region": str(row.get("Industry / Region") or "").strip(),
                        "ipo_date": str(row.get("IPO Date") or "").strip(),
                        "key_pre_ipo_claims": str(row.get("Key Pre-IPO Claim(s)") or "").strip(),
                        "long_term_outcome": str(row.get("Long-term Outcome (IPO to Apr 2026)") or "").strip(),
                        "forecast_error": str(row.get("Forecast Error") or "").strip(),
                        "predicted_pattern": str(row.get("Predicted Pattern (pre-IPO basis)") or "").strip(),
                        "source_table": filename,
                    }
                )

    canonical_records: list[CanonicalReferenceRecord] = []
    for rows in grouped.values():
        pattern_labels = [r["predicted_pattern"] for r in rows if r["predicted_pattern"]]
        pattern_ids = [pid for pid, _label in (_pattern_parts(label) for label in pattern_labels) if pid is not None]
        chosen_pattern = _pick_canonical_value(
            [(str(r["predicted_pattern"]), str(r["source_table"])) for r in rows if r["predicted_pattern"]]
        )
        chosen_pattern_id, _ = _pattern_parts(chosen_pattern)
        ambiguous_patterns = sorted({label for label in pattern_labels if label and label != chosen_pattern})
        if chosen_pattern_id is None and pattern_ids:
            chosen_pattern_id = Counter(pattern_ids).most_common(1)[0][0]

        canonical_records.append(
            CanonicalReferenceRecord(
                company_name=_pick_canonical_value([(r["company_name"], r["source_table"]) for r in rows]),
                ticker=_pick_canonical_value([(r["ticker"] or "", r["source_table"]) for r in rows]) or None,
                company_ticker=_pick_canonical_value([(r["company_ticker"], r["source_table"]) for r in rows]),
                industry_region=_pick_canonical_value([(r["industry_region"], r["source_table"]) for r in rows]),
                ipo_date=_pick_canonical_value([(r["ipo_date"], r["source_table"]) for r in rows]),
                key_pre_ipo_claims=_pick_canonical_value([(r["key_pre_ipo_claims"], r["source_table"]) for r in rows]),
                long_term_outcome=_pick_canonical_value([(r["long_term_outcome"], r["source_table"]) for r in rows]),
                forecast_error=_pick_canonical_value([(r["forecast_error"], r["source_table"]) for r in rows]),
                predicted_pattern=chosen_pattern,
                predicted_pattern_id=chosen_pattern_id,
                source_tables=sorted({str(r["source_table"]) for r in rows}),
                ambiguous_patterns=ambiguous_patterns,
            )
        )
    canonical_records.sort(key=lambda record: (record.company_name.lower(), record.ticker or ""))
    return canonical_records


def lookup_reference_record(company_name: str, ticker: str | None) -> CanonicalReferenceRecord | None:
    ticker_norm = ticker.strip().upper() if ticker else None
    company_key = _normalize_company_key(company_name)
    for record in load_canonical_reference_dataset():
        if ticker_norm and record.ticker == ticker_norm:
            return record
        if _normalize_company_key(record.company_name) == company_key:
            return record
    return None


def _pattern_analogs(pattern_id: int | None, exclude_ticker: str | None = None) -> list[CanonicalReferenceRecord]:
    if pattern_id is None:
        return []
    exclude_norm = exclude_ticker.strip().upper() if exclude_ticker else None
    analogs = [r for r in load_canonical_reference_dataset() if r.predicted_pattern_id == pattern_id]
    if exclude_norm:
        analogs = [r for r in analogs if r.ticker != exclude_norm]
    return analogs


def _heuristic_pattern_id(
    *,
    company_name: str,
    business_model: str,
    ipo_date: date | None,
    outcome_metrics: OutcomeMetrics | None,
    claim_checks: list[ClaimCheck],
    patterns_flagged: list[Any],
) -> int:
    missed = sum(1 for check in claim_checks if check.status == "missed")
    supported = sum(1 for check in claim_checks if check.status == "supported")
    current_perf = outcome_metrics.performance_since_ipo_pct if outcome_metrics else None
    signals = " ".join(str(getattr(flag, "signal", "")) for flag in patterns_flagged).lower()
    business_lower = business_model.lower()
    if "lockup" in signals or "insider" in signals:
        return 10
    if ipo_date and ipo_date.year in (2020, 2021):
        return 11
    if "spac" in business_lower:
        return 6
    if current_perf is not None and current_perf <= -25 and missed >= supported:
        return 1
    if current_perf is not None and current_perf >= 25 and supported >= missed:
        return 2
    return 4


def _pattern_label_for_id(pattern_id: int) -> str:
    labels = {
        1: "Pattern 1: Hyped growth story, weak long-run performance",
        2: "Pattern 2: Steady compounders with conservative narratives",
        3: "Pattern 3: Mega-IPOs with strong debuts but modest long-run returns",
        4: "Pattern 4: Profitless growth that eventually inflects",
        5: "Pattern 5: Hot-issue cohorts with broad underperformance",
        6: "Pattern 6: SPAC projections and post-merger collapses",
        7: "Pattern 7: Forward-looking customer metrics as credible signals",
        8: "Pattern 8: Prospectus content and topic mix predicting outcomes",
        9: "Pattern 9: Analyst coverage and pre-IPO attention",
        10: "Pattern 10: Lock-up expiries, insider selling, and narrative shifts",
        11: "Pattern 11: IPO timing, macro regime, and post-IPO mean reversion",
        12: "Pattern 12: Pre-IPO information predicts downside risk better than upside",
    }
    return labels.get(pattern_id, f"Pattern {pattern_id}: heuristic classification")


def _derived_claim_text(parser_output: dict[str, Any], prediction_claims: list[PredictionClaim]) -> list[str]:
    claims: list[str] = []
    business_model = str(parser_output.get("business_model") or "").strip()
    if business_model:
        claims.append(business_model[:260])
    financials = parser_output.get("financials") if isinstance(parser_output.get("financials"), dict) else {}
    growth = financials.get("revenue_growth_yoy")
    if isinstance(growth, (int, float)):
        claims.append(f"Filed revenue growth around {float(growth):.1f}% year over year.")
    demand = parser_output.get("demand_signals") if isinstance(parser_output.get("demand_signals"), dict) else {}
    roadshow = str(demand.get("roadshow_sentiment") or "").strip()
    if roadshow and not roadshow.lower().startswith("no clear roadshow"):
        claims.append(roadshow[:220])
    for claim in prediction_claims:
        text = claim.prediction_text.strip()
        if text:
            claims.append(text[:220])
        if len(claims) >= 4:
            break
    seen: list[str] = []
    for claim in claims:
        if claim not in seen:
            seen.append(claim)
    return seen[:3]


def _derived_long_term_outcome(
    *,
    company_name: str,
    outcome_metrics: OutcomeMetrics | None,
    delivery_verdict: str | None,
) -> str:
    if outcome_metrics is None:
        return f"{company_name}: post-IPO price performance unavailable."
    pieces = []
    if outcome_metrics.ipo_price is not None:
        pieces.append(f"IPO {outcome_metrics.ipo_price:.2f}")
    if outcome_metrics.current_price is not None:
        pieces.append(f"current {outcome_metrics.current_price:.2f}")
    if outcome_metrics.performance_since_ipo_pct is not None:
        pieces.append(f"since IPO {outcome_metrics.performance_since_ipo_pct:+.1f}%")
    if outcome_metrics.peak_price is not None:
        pieces.append(f"peak {outcome_metrics.peak_price:.2f}")
    if outcome_metrics.trough_price is not None:
        pieces.append(f"trough {outcome_metrics.trough_price:.2f}")
    if not pieces:
        return f"{company_name}: post-IPO price performance unavailable."
    verdict_text = f"; delivery verdict {delivery_verdict}" if delivery_verdict else ""
    return f"{company_name}: " + ", ".join(pieces) + verdict_text + "."


def _derived_forecast_error(claim_checks: list[ClaimCheck]) -> str:
    if not claim_checks:
        return "Post-IPO forecast error unavailable from current evidence."
    supported = sum(1 for check in claim_checks if check.status == "supported")
    missed = sum(1 for check in claim_checks if check.status == "missed")
    if missed > supported:
        return "Post-IPO results underdelivered versus the main S-1 framing."
    if supported > missed:
        return "Post-IPO results broadly aligned with the main S-1 framing."
    return "Post-IPO results were mixed versus the main S-1 framing."


def _industry_region_from_yahoo(yahoo_finance_data: dict[str, Any] | None) -> str:
    if not yahoo_finance_data:
        return "unavailable"
    industry = str(yahoo_finance_data.get("industry") or "").strip()
    sector = str(yahoo_finance_data.get("sector") or "").strip()
    country = str(yahoo_finance_data.get("country") or "").strip()
    exchange = str(yahoo_finance_data.get("exchange") or "").strip()
    left = industry or sector
    right = country or exchange
    if left and right:
        return f"{left} / {right}"
    if left:
        return left
    if right:
        return right
    return "unavailable"


def _analog_records_for_profile(
    *,
    pattern_id: int | None,
    ticker: str | None,
    industry_region: str,
    comparable_tickers: list[str],
) -> list[CanonicalReferenceRecord]:
    if pattern_id is not None:
        analogs = _pattern_analogs(pattern_id, exclude_ticker=ticker)
        if analogs:
            return analogs[:5]
    industry_tokens = _industry_tokens(industry_region)
    comparable_set = {ticker.upper() for ticker in comparable_tickers}
    scored: list[tuple[int, CanonicalReferenceRecord]] = []
    for record in load_canonical_reference_dataset():
        if ticker and record.ticker == ticker:
            continue
        score = 0
        if record.ticker and record.ticker in comparable_set:
            score += 5
        score += len(industry_tokens & _industry_tokens(record.industry_region))
        if score > 0:
            scored.append((score, record))
    scored.sort(key=lambda item: (item[0], item[1].company_name), reverse=True)
    return [record for _score, record in scored[:5]]


def build_output_contract_bundle(
    *,
    company_name: str,
    ticker: str | None,
    ipo_date: date | None,
    parser_output: dict[str, Any],
    scenario_output: dict[str, Any],
    outcome_metrics: OutcomeMetrics | None,
    prediction_claims: list[PredictionClaim],
    claim_checks: list[ClaimCheck],
    patterns_flagged: list[Any],
    comparable_tickers: list[str] | None = None,
    yahoo_finance_data: dict[str, Any] | None = None,
) -> OutputContractBundle:
    reference = lookup_reference_record(company_name=company_name, ticker=ticker)
    comparable_tickers = comparable_tickers or []
    if reference is not None:
        delivery_verdict = str(scenario_output.get("ipo_delivery_verdict") or "").strip() or None
        long_term_outcome_line = _resolved_long_term_outcome_line(
            company_name=company_name,
            outcome_metrics=outcome_metrics,
            delivery_verdict=delivery_verdict,
            fallback_line=reference.long_term_outcome,
        )
        company_profile = CompanyProfile(
            issuer_name=reference.company_name,
            ticker=reference.ticker,
            company_ticker=reference.company_ticker,
            industry_region=reference.industry_region or "unavailable",
            ipo_date=ipo_date,
            listing_type=str(parser_output.get("offering_type") or "unavailable"),
        )
        pre_ipo_thesis = PreIpoThesis(
            key_pre_ipo_claims=[reference.key_pre_ipo_claims],
            source_document_types=["reference_table", "s1_prospectus", "roadshow_or_media"],
            source_excerpts=[reference.key_pre_ipo_claims],
        )
        realized_outcome = RealizedOutcome(
            long_term_outcome=long_term_outcome_line,
            forecast_error=reference.forecast_error,
        )
        analog_records = _analog_records_for_profile(
            pattern_id=reference.predicted_pattern_id,
            ticker=reference.ticker,
            industry_region=reference.industry_region,
            comparable_tickers=comparable_tickers,
        )
        pattern_classification = PatternClassification(
            primary_pattern_id=reference.predicted_pattern_id,
            primary_pattern_label=reference.predicted_pattern,
            confidence="high" if not reference.ambiguous_patterns else "medium",
            rationale="Exact match from canonical reference dataset.",
            analog_companies=[record.company_ticker for record in analog_records[:3]],
            secondary_pattern_labels=reference.ambiguous_patterns,
            source="reference_exact",
        )
        table_row = ReferenceTableRow(
            company_ticker=reference.company_ticker,
            industry_region=reference.industry_region or "unavailable",
            ipo_date=reference.ipo_date or _safe_iso_date(ipo_date),
            key_pre_ipo_claims=reference.key_pre_ipo_claims or "unavailable",
            long_term_outcome=long_term_outcome_line,
            forecast_error=reference.forecast_error or "unavailable",
            predicted_pattern=reference.predicted_pattern or "unavailable",
        )
        return OutputContractBundle(
            company_profile=company_profile,
            pre_ipo_thesis=pre_ipo_thesis,
            realized_outcome=realized_outcome,
            pattern_classification=pattern_classification,
            reference_table_row=table_row,
        )

    derived_claims = _derived_claim_text(parser_output, prediction_claims)
    industry_region = _industry_region_from_yahoo(yahoo_finance_data)
    business_model = str(parser_output.get("business_model") or "")
    heuristic_pattern_id = _heuristic_pattern_id(
        company_name=company_name,
        business_model=business_model,
        ipo_date=ipo_date,
        outcome_metrics=outcome_metrics,
        claim_checks=claim_checks,
        patterns_flagged=patterns_flagged,
    )
    analog_records = _analog_records_for_profile(
        pattern_id=heuristic_pattern_id,
        ticker=ticker,
        industry_region=industry_region,
        comparable_tickers=comparable_tickers,
    )
    pattern_label = _pattern_label_for_id(heuristic_pattern_id)
    table_company = f"{company_name} ({ticker})" if ticker else company_name
    company_profile = CompanyProfile(
        issuer_name=company_name,
        ticker=ticker,
        company_ticker=table_company,
        industry_region=industry_region,
        ipo_date=ipo_date,
        listing_type=str(parser_output.get("offering_type") or "unavailable"),
    )
    pre_ipo_thesis = PreIpoThesis(
        key_pre_ipo_claims=derived_claims or ["unavailable"],
        source_document_types=["s1_prospectus", "roadshow_or_media"],
        source_excerpts=derived_claims[:2],
    )
    realized_outcome = RealizedOutcome(
        long_term_outcome=_resolved_long_term_outcome_line(
            company_name=company_name,
            outcome_metrics=outcome_metrics,
            delivery_verdict=str(scenario_output.get("ipo_delivery_verdict") or "").strip() or None,
        ),
        forecast_error=_derived_forecast_error(claim_checks),
    )
    pattern_classification = PatternClassification(
        primary_pattern_id=heuristic_pattern_id,
        primary_pattern_label=pattern_label,
        confidence="medium",
        rationale="Heuristic mapping from claim checks, price performance, IPO timing, and scenario signals.",
        analog_companies=[record.company_ticker for record in analog_records[:3]],
        source="heuristic",
    )
    table_row = ReferenceTableRow(
        company_ticker=table_company,
        industry_region=industry_region,
        ipo_date=_safe_iso_date(ipo_date),
        key_pre_ipo_claims=" | ".join(pre_ipo_thesis.key_pre_ipo_claims) if pre_ipo_thesis.key_pre_ipo_claims else "unavailable",
        long_term_outcome=realized_outcome.long_term_outcome,
        forecast_error=realized_outcome.forecast_error,
        predicted_pattern=pattern_label,
    )
    return OutputContractBundle(
        company_profile=company_profile,
        pre_ipo_thesis=pre_ipo_thesis,
        realized_outcome=realized_outcome,
        pattern_classification=pattern_classification,
        reference_table_row=table_row,
    )
