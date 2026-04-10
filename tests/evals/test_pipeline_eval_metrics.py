from __future__ import annotations

import asyncio
import logging

from backend.models.single_agent_result import SingleAgentResult
from tests.evals.load_gold import merged_eval_dataset
from tests.evals.pipeline_prediction_mapper import single_agent_result_to_case_prediction
from tests.evals.run_pipeline_case import run_pipeline_case
from tests.evals.scoring import CasePrediction, metrics_summary_line, score_dataset


async def _run_pipeline_predictions() -> tuple[dict[str, CasePrediction], dict[str, int]]:
    dataset = merged_eval_dataset()
    predictions: dict[str, CasePrediction] = {}
    skip_counts: dict[str, int] = {}
    scoreable_claims = 0
    skipped_claims = 0

    for case in dataset.cases:
        run_result = await run_pipeline_case(
            case=case,
            inject_post_ipo_10k=(case.expected_label == "contradiction"),
        )
        final_report = run_result.final_report or {}
        parser_output = run_result.parser_output or {}
        scenario_output = run_result.scenario_output or {}
        result = SingleAgentResult.model_validate(final_report)
        mapped, stats = single_agent_result_to_case_prediction(
            case=case,
            parser_output=parser_output,
            scenario_output=scenario_output,
            result=result,
        )
        predictions[case.case_id] = mapped
        scoreable_claims += stats.scoreable_claims
        skipped_claims += stats.skipped_claims
        for reason, count in stats.skipped_by_reason.items():
            skip_counts[reason] = skip_counts.get(reason, 0) + count

    skip_counts["_scoreable_claims"] = scoreable_claims
    skip_counts["_skipped_claims"] = skipped_claims
    return predictions, skip_counts


def test_pipeline_eval_metrics(caplog) -> None:
    dataset = merged_eval_dataset()
    predictions, skip_counts = asyncio.run(_run_pipeline_predictions())
    metrics = score_dataset(dataset, predictions)

    summary = "EVAL_PIPELINE_" + metrics_summary_line(metrics)
    caplog.set_level(logging.WARNING)
    logging.getLogger("evals").warning(summary)

    skip_line = (
        "EVAL_PIPELINE_SKIPS "
        f"scoreable_claims={skip_counts.get('_scoreable_claims', 0)} "
        f"skipped_claims={skip_counts.get('_skipped_claims', 0)} "
        f"skipped_by_reason={{{', '.join(f'{k}:{v}' for k, v in sorted(skip_counts.items()) if not k.startswith('_'))}}}"
    )
    logging.getLogger("evals").warning(skip_line)

    assert summary in caplog.text
    assert "EVAL_PIPELINE_SKIPS" in caplog.text
    assert metrics.claim_precision >= 0.85
    assert metrics.claim_recall >= 0.85
    assert metrics.contradiction_recall >= 0.75
    assert metrics.hallucination_fpr <= 0.1
    assert skip_counts.get("_scoreable_claims", 0) > 0
    assert skip_counts.get("_skipped_claims", 0) >= 0
