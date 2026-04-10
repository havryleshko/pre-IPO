import logging

from tests.evals.load_gold import load_reddit_round1
from tests.evals.predictor_baseline import predict_case_baseline
from tests.evals.scoring import metrics_summary_line, score_dataset


def test_reddit_round1_metrics_baseline(caplog) -> None:
    dataset = load_reddit_round1()
    predictions = {case.case_id: predict_case_baseline(case) for case in dataset.cases}
    metrics = score_dataset(dataset, predictions)

    summary = metrics_summary_line(metrics)
    caplog.set_level(logging.WARNING)
    logging.getLogger("evals").warning(summary)

    assert summary in caplog.text
    assert metrics.claim_precision >= 0.50
    assert metrics.claim_recall >= 0.50
    assert metrics.contradiction_recall >= 0.66
    assert metrics.hallucination_fpr <= 0.40
