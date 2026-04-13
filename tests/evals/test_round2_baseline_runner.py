from __future__ import annotations

from tests.evals.run_round2_baseline import CompanyCohortRow, _cohort_summary
from tests.evals.round2_cohorts import validate_reference_exact_cohort


def test_reference_exact_cohort_is_canonical() -> None:
    assert validate_reference_exact_cohort() == []


def test_cohort_summary_aggregates_rows() -> None:
    rows = [
        CompanyCohortRow(
            cohort="heuristic_9",
            input_company="A",
            analysis_id="a1",
            status="completed",
            company_name="A",
            resolved_ticker="A",
            bucket="heuristic",
            row_source="heuristic",
            industry_region_source="yahoo_info",
            mandatory_present=7,
            mandatory_total=7,
            missing_fields=[],
            projection_complete=True,
            analog_companies_present=True,
            projection_basis_present=True,
            predicted_pattern="Pattern 11",
            pattern_id=11,
            reference_company_ticker=None,
        ),
        CompanyCohortRow(
            cohort="heuristic_9",
            input_company="B",
            analysis_id="b1",
            status="completed",
            company_name="B",
            resolved_ticker="B",
            bucket="heuristic",
            row_source="heuristic",
            industry_region_source="yahoo_info",
            mandatory_present=6,
            mandatory_total=7,
            missing_fields=["ipo_date"],
            projection_complete=False,
            analog_companies_present=False,
            projection_basis_present=False,
            predicted_pattern="Pattern 4",
            pattern_id=4,
            reference_company_ticker=None,
        ),
    ]
    summary = _cohort_summary(rows, reference_metrics=None)
    assert summary["total_inputs"] == 2
    assert summary["completed"] == 2
    assert summary["reference_exact"] == 0
    assert summary["heuristic"] == 2
    assert summary["mandatory_field_coverage"] == 13 / 14
    assert summary["projection_completeness"] == 0.5
    assert summary["missing_field_distribution"] == {"ipo_date": 1}
