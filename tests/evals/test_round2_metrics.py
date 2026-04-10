import logging

from tests.evals.load_gold import merged_eval_dataset
from tests.evals.predictor_baseline import predict_case_baseline
from tests.evals.scoring import metrics_summary_line, score_dataset

FLOOR_CLAIM_PRECISION = 0.90
FLOOR_CLAIM_RECALL = 0.90
FLOOR_CONTRADICTION_RECALL = 0.75
CEILING_HALLUCINATION_FPR = 0.15


def test_merged_eval_metrics_baseline(caplog) -> None:
    dataset = merged_eval_dataset()
    predictions = {case.case_id: predict_case_baseline(case) for case in dataset.cases}
    metrics = score_dataset(dataset, predictions)

    summary = metrics_summary_line(metrics)
    caplog.set_level(logging.WARNING)
    logging.getLogger("evals").warning(summary)

    assert summary in caplog.text
    assert metrics.claim_precision >= FLOOR_CLAIM_PRECISION
    assert metrics.claim_recall >= FLOOR_CLAIM_RECALL
    assert metrics.contradiction_recall >= FLOOR_CONTRADICTION_RECALL
    assert metrics.hallucination_fpr <= CEILING_HALLUCINATION_FPR
