from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from backend.models.eval_case import EvalCase, EvalClaim, EvalContradiction, EvalDataset


@dataclass
class PredictedClaim:
    claim_id: str
    claim_value: float | None = None
    claim_text: str | None = None


@dataclass
class PredictedContradiction:
    claim_id: str
    contradiction_type: str
    derived_output_value: float | None = None


@dataclass
class CasePrediction:
    case_id: str
    extracted_claims: list[PredictedClaim] = field(default_factory=list)
    contradictions: list[PredictedContradiction] = field(default_factory=list)

    @property
    def has_contradiction(self) -> bool:
        return len(self.contradictions) > 0


@dataclass
class EvalMetrics:
    claim_precision: float
    claim_recall: float
    contradiction_recall: float
    hallucination_fpr: float
    claim_tp: int
    claim_fp: int
    claim_fn: int
    contradiction_hits: int
    contradiction_total: int
    hallucinations: int
    no_contradiction_total: int
    failing_case_ids: list[str]


def metrics_summary_line(metrics: EvalMetrics) -> str:
    failing = ",".join(metrics.failing_case_ids) if metrics.failing_case_ids else "-"
    return (
        "EVAL_METRICS "
        f"claim_precision={metrics.claim_precision:.4f} "
        f"claim_recall={metrics.claim_recall:.4f} "
        f"contradiction_recall={metrics.contradiction_recall:.4f} "
        f"hallucination_fpr={metrics.hallucination_fpr:.4f} "
        f"failing_case_ids={failing}"
    )


def _is_close(value: float, target: float, tolerance: float) -> bool:
    return abs(value - target) <= tolerance


def _claim_matches(gold: EvalClaim, predicted: PredictedClaim) -> bool:
    if gold.claim_value is None:
        if not predicted.claim_text:
            return False
        return gold.claim_text.lower() in predicted.claim_text.lower()
    if predicted.claim_value is None:
        return False
    mode = gold.comparison_mode
    target = gold.claim_value
    if mode == "exact_match":
        return _is_close(predicted.claim_value, target, 1e-6)
    if mode == "approximate_match":
        tolerance = max(1.0, abs(target) * 0.05)
        return _is_close(predicted.claim_value, target, tolerance)
    if mode == "floor_claim":
        return predicted.claim_value >= target
    if mode == "derived_numeric_check":
        tolerance = max(0.1, abs(target) * 0.05)
        return _is_close(predicted.claim_value, target, tolerance)
    return False


def _contradiction_matches(gold: EvalContradiction, predicted: PredictedContradiction) -> bool:
    if predicted.claim_id != gold.claim_id:
        return False
    if predicted.contradiction_type != gold.contradiction_type:
        return False
    if gold.contradiction_type == "derived_numeric_contradiction" and gold.derived_output_value is not None:
        if predicted.derived_output_value is None:
            return False
        tolerance = max(0.1, abs(gold.derived_output_value) * 0.05)
        return _is_close(predicted.derived_output_value, gold.derived_output_value, tolerance)
    return True


def _index_claims(claims: Iterable[PredictedClaim]) -> dict[str, PredictedClaim]:
    return {claim.claim_id: claim for claim in claims}


def score_dataset(dataset: EvalDataset, predictions: dict[str, CasePrediction]) -> EvalMetrics:
    claim_tp = 0
    claim_fn = 0
    claim_fp = 0
    contradiction_hits = 0
    contradiction_total = 0
    hallucinations = 0
    no_contradiction_total = 0
    failing_case_ids: list[str] = []

    for case in dataset.cases:
        pred = predictions.get(case.case_id, CasePrediction(case_id=case.case_id))
        pred_by_id = _index_claims(pred.extracted_claims)
        case_failed = False

        for gold_claim in case.claims_to_extract:
            predicted_claim = pred_by_id.get(gold_claim.claim_id)
            if predicted_claim is None:
                claim_fn += 1
                case_failed = True
                continue
            if _claim_matches(gold_claim, predicted_claim):
                claim_tp += 1
            else:
                claim_fn += 1
                case_failed = True

        gold_claim_ids = {claim.claim_id for claim in case.claims_to_extract}
        for predicted_claim in pred.extracted_claims:
            if predicted_claim.claim_id not in gold_claim_ids:
                claim_fp += 1
                case_failed = True

        if case.expected_label == "contradiction":
            contradiction_total += 1
            matched = False
            for gold_contradiction in case.contradictions:
                if any(_contradiction_matches(gold_contradiction, pc) for pc in pred.contradictions):
                    matched = True
                    break
            if matched:
                contradiction_hits += 1
            else:
                case_failed = True
        else:
            no_contradiction_total += 1
            if pred.has_contradiction:
                hallucinations += 1
                case_failed = True

        if case_failed:
            failing_case_ids.append(case.case_id)

    claim_precision = claim_tp / (claim_tp + claim_fp) if (claim_tp + claim_fp) else 0.0
    claim_recall = claim_tp / (claim_tp + claim_fn) if (claim_tp + claim_fn) else 0.0
    contradiction_recall = contradiction_hits / contradiction_total if contradiction_total else 0.0
    hallucination_fpr = hallucinations / no_contradiction_total if no_contradiction_total else 0.0

    return EvalMetrics(
        claim_precision=claim_precision,
        claim_recall=claim_recall,
        contradiction_recall=contradiction_recall,
        hallucination_fpr=hallucination_fpr,
        claim_tp=claim_tp,
        claim_fp=claim_fp,
        claim_fn=claim_fn,
        contradiction_hits=contradiction_hits,
        contradiction_total=contradiction_total,
        hallucinations=hallucinations,
        no_contradiction_total=no_contradiction_total,
        failing_case_ids=failing_case_ids,
    )
