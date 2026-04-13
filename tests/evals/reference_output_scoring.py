from __future__ import annotations

from dataclasses import dataclass
import re

from backend.models.single_agent_result import SingleAgentResult
from backend.services.reference_output_contract import CanonicalReferenceRecord


@dataclass
class ReferenceOutputMetrics:
    mandatory_field_coverage: float
    pattern_accuracy: float
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

        if case_failed:
            failing_company_ids.append(key)

    return ReferenceOutputMetrics(
        mandatory_field_coverage=(mandatory_hits / mandatory_total) if mandatory_total else 0.0,
        pattern_accuracy=(pattern_hits / pattern_total) if pattern_total else 0.0,
        failing_company_ids=failing_company_ids,
    )
