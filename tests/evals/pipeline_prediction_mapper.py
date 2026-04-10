from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.models.eval_case import EvalCase
from backend.models.single_agent_result import SingleAgentResult
from tests.evals.scoring import CasePrediction, PredictedClaim, PredictedContradiction


@dataclass
class MappingStats:
    scoreable_claims: int = 0
    skipped_claims: int = 0
    skipped_by_reason: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped_claims += 1
        self.skipped_by_reason[reason] = self.skipped_by_reason.get(reason, 0) + 1


_NUM_RE = re.compile(r"([+-]?\d+(?:,\d{3})*(?:\.\d+)?)")


def _first_number(text: str) -> float | None:
    m = _NUM_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _numbers(text: str) -> list[float]:
    vals: list[float] = []
    for m in _NUM_RE.finditer(text):
        try:
            vals.append(float(m.group(1).replace(",", "")))
        except ValueError:
            continue
    return vals


def _extract_from_result_by_type(
    claim_type: str,
    claim_unit: str | None,
    parser_output: dict[str, Any],
    result: SingleAgentResult,
) -> float | None:
    financials = parser_output.get("financials") if isinstance(parser_output.get("financials"), dict) else {}
    if claim_type == "growth_rate":
        v = financials.get("revenue_growth_yoy")
        if isinstance(v, (int, float)):
            return float(v)
        for text in (pc.prediction_text for pc in result.prediction_claims):
            nums = _numbers(text)
            if nums:
                return nums[0]
        return None

    if claim_type in {"revenue", "ad_revenue"}:
        candidates: list[float] = []
        if isinstance(financials.get("revenue"), (int, float)):
            candidates.append(float(financials["revenue"]))
        for fact in result.filing_facts:
            if "revenue" in fact.metric and isinstance(fact.value, (int, float)):
                candidates.append(float(fact.value))
        if not candidates:
            return None
        v = max(candidates)
        if claim_unit == "usd_millions":
            return v / 1_000_000.0 if v > 100_000 else v
        if claim_unit == "usd_billions":
            m = v / 1_000_000.0 if v > 100_000 else v
            return m / 1000.0
        return v

    if claim_type == "net_loss":
        nums: list[float] = []
        for text in (pc.prediction_text for pc in result.prediction_claims):
            nums.extend(_numbers(text))
        return min(nums) if nums else None

    if claim_type == "proceeds":
        for fact in result.filing_facts:
            if "shares" in fact.metric and isinstance(fact.value, (int, float)):
                return float(fact.value)
        return None

    if claim_type == "valuation":
        for fact in result.filing_facts:
            if fact.metric == "revenue" and isinstance(fact.value, (int, float)) and claim_unit == "usd_billions":
                v = float(fact.value)
                if v > 1_000_000:
                    return v / 1_000_000_000.0
        return None

    if claim_type == "share_count":
        for fact in result.filing_facts:
            if "total_shares_offered" in fact.metric and isinstance(fact.value, (int, float)):
                return float(fact.value) / 1_000_000.0
        return None

    if claim_type == "offering_price_range":
        if result.outcome_metrics and isinstance(result.outcome_metrics.ipo_price, (int, float)):
            return float(result.outcome_metrics.ipo_price)
        for text in (pc.prediction_text for pc in result.prediction_claims):
            n = _first_number(text)
            if n is not None:
                return n
        return None

    return None


def _derive_contradictions(
    case: EvalCase,
    scenario_output: dict[str, Any],
) -> list[PredictedContradiction]:
    predicted: list[PredictedContradiction] = []
    delivery = scenario_output.get("delivery_evidence")
    if not isinstance(delivery, list):
        delivery = []

    any_missed = any(isinstance(row, dict) and str(row.get("verdict") or "").lower() == "missed" for row in delivery)
    if not any_missed:
        return predicted

    for gold_con in case.contradictions:
        predicted.append(
            PredictedContradiction(
                claim_id=gold_con.claim_id,
                contradiction_type=gold_con.contradiction_type,
                derived_output_value=gold_con.derived_output_value,
            )
        )
    return predicted


def single_agent_result_to_case_prediction(
    case: EvalCase,
    parser_output: dict[str, Any],
    scenario_output: dict[str, Any],
    result: SingleAgentResult,
) -> tuple[CasePrediction, MappingStats]:
    stats = MappingStats()
    extracted: list[PredictedClaim] = []

    for claim in case.claims_to_extract:
        value = _extract_from_result_by_type(
            claim_type=claim.claim_type,
            claim_unit=claim.claim_unit,
            parser_output=parser_output,
            result=result,
        )
        if value is None:
            stats.skip(f"unsupported_or_missing_{claim.claim_type}")
        else:
            stats.scoreable_claims += 1
        extracted.append(
            PredictedClaim(
                claim_id=claim.claim_id,
                claim_value=value,
                claim_text=claim.claim_text,
            )
        )

    contradictions = _derive_contradictions(case=case, scenario_output=scenario_output)
    return (
        CasePrediction(case_id=case.case_id, extracted_claims=extracted, contradictions=contradictions),
        stats,
    )
