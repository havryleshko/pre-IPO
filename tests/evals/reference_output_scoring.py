from __future__ import annotations

from dataclasses import dataclass
import re

from backend.models.single_agent_result import SingleAgentResult
from backend.services.reference_output_contract import CanonicalReferenceRecord


@dataclass
class ReferenceOutputMetrics:
    mandatory_field_coverage: float
    pattern_accuracy: float
    projection_field_coverage: float
    decline_band_hit_rate: float
    rebound_signal_accuracy: float
    failing_company_ids: list[str]


def _company_key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _prediction_index(predictions: dict[str, SingleAgentResult]) -> dict[str, SingleAgentResult]:
    indexed: dict[str, SingleAgentResult] = {}
    for key, result in predictions.items():
        indexed[_company_key(key)] = result
        indexed[_company_key(result.company_name)] = result
        if result.company_profile and result.company_profile.ticker:
            indexed[_company_key(result.company_profile.ticker)] = result
    return indexed


def _has_text(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().lower()
    if not normalized:
        return False
    normalized = re.sub(r"^[\W_]+|[\W_]+$", "", normalized)
    if not normalized:
        return False
    placeholder_values = {"unavailable", "n/a", "na", "none", "null", "unknown", "tbd"}
    return normalized not in placeholder_values


def score_reference_outputs(
    expected_rows: list[CanonicalReferenceRecord],
    predictions: dict[str, SingleAgentResult],
) -> ReferenceOutputMetrics:
    indexed = _prediction_index(predictions)
    mandatory_hits = 0
    mandatory_total = 0
    pattern_hits = 0
    pattern_total = 0
    projection_hits = 0
    projection_total = 0
    decline_hits = 0
    decline_total = 0
    rebound_hits = 0
    rebound_total = 0
    failing_company_ids: list[str] = []

    for row in expected_rows:
        key = row.ticker or row.company_name
        pred = indexed.get(_company_key(key))
        if pred is None:
            failing_company_ids.append(key)
            continue
        case_failed = False

        ref_row = pred.reference_table_row
        for value in (
            ref_row.company_ticker if ref_row else None,
            ref_row.industry_region if ref_row else None,
            ref_row.ipo_date if ref_row else None,
            ref_row.key_pre_ipo_claims if ref_row else None,
            ref_row.long_term_outcome if ref_row else None,
            ref_row.forecast_error if ref_row else None,
            ref_row.predicted_pattern if ref_row else None,
        ):
            mandatory_total += 1
            if _has_text(value):
                mandatory_hits += 1
            else:
                case_failed = True

        pattern_total += 1
        if ref_row and row.predicted_pattern_id is not None and f"Pattern {row.predicted_pattern_id}" in ref_row.predicted_pattern:
            pattern_hits += 1
        else:
            case_failed = True

        projection = pred.ipo_projection
        projection_total += 1
        if (
            projection
            and projection.likely_decline_band_pct is not None
            and projection.likely_time_to_trough_months is not None
            and projection.rebound_probability_band is not None
            and projection.likely_time_to_rebound_months is not None
        ):
            projection_hits += 1
        else:
            case_failed = True

        outcome = pred.outcome_metrics
        if (
            projection
            and outcome
            and outcome.ipo_price is not None
            and outcome.ipo_price > 0
            and outcome.trough_price is not None
            and projection.likely_decline_band_pct is not None
            and projection.likely_decline_band_pct.low is not None
            and projection.likely_decline_band_pct.high is not None
        ):
            decline_total += 1
            actual_decline_pct = ((outcome.trough_price - outcome.ipo_price) / outcome.ipo_price) * 100.0
            lower = min(projection.likely_decline_band_pct.low, projection.likely_decline_band_pct.high)
            upper = max(projection.likely_decline_band_pct.low, projection.likely_decline_band_pct.high)
            if lower <= actual_decline_pct <= upper:
                decline_hits += 1
            else:
                case_failed = True

        if (
            projection
            and outcome
            and projection.rebound_probability_band is not None
            and projection.rebound_probability_band.low is not None
            and projection.rebound_probability_band.high is not None
        ):
            rebound_total += 1
            recovered = outcome.recovered_to_ipo_date is not None
            midpoint = (projection.rebound_probability_band.low + projection.rebound_probability_band.high) / 2.0
            predicted_recovery = midpoint >= 50.0
            if recovered == predicted_recovery:
                rebound_hits += 1
            else:
                case_failed = True

        if case_failed:
            failing_company_ids.append(key)

    return ReferenceOutputMetrics(
        mandatory_field_coverage=(mandatory_hits / mandatory_total) if mandatory_total else 0.0,
        pattern_accuracy=(pattern_hits / pattern_total) if pattern_total else 0.0,
        projection_field_coverage=(projection_hits / projection_total) if projection_total else 0.0,
        decline_band_hit_rate=(decline_hits / decline_total) if decline_total else 0.0,
        rebound_signal_accuracy=(rebound_hits / rebound_total) if rebound_total else 0.0,
        failing_company_ids=failing_company_ids,
    )
