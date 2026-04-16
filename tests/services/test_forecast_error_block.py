from __future__ import annotations

from datetime import date

from backend.models.single_agent_result import ClaimCheck, OutcomeMetrics, PredictionClaim
from backend.services.reference_output_contract import build_output_contract_bundle


def test_forecast_error_block_has_exact_four_lines_and_labels() -> None:
    bundle = build_output_contract_bundle(
        company_name="TestCo",
        ticker="TCO",
        ipo_date=date(2021, 1, 1),
        parser_output={"business_model": "B2B software platform.", "offering_type": "primary"},
        scenario_output={"ipo_delivery_verdict": "mixed"},
        outcome_metrics=OutcomeMetrics(ipo_price=10.0, current_price=12.0, performance_since_ipo_pct=20.0),
        prediction_claims=[PredictionClaim(claim_id="c1", claim_type="growth", prediction_text="Growth.", source="SEC")],
        claim_checks=[ClaimCheck(claim_id="c1", status="supported")],
        patterns_flagged=[],
        comparable_tickers=[],
        s1_disclosure_checks=[
            ClaimCheck(
                claim_id="Revenue growth guidance present?",
                status="supported",
                evidence_quotes=["We believe the market will grow at a 20% CAGR and expect revenue to scale accordingly."],
            ),
            ClaimCheck(
                claim_id="Profitability timeline mentioned?",
                status="supported",
                evidence_quotes=["We expect to achieve profitability by 2023 as scale improves."],
            ),
        ],
        post_ipo_10k=(
            "Years ended December 31, 2023, 2022 and 2021 "
            "Total revenue 300 200 100 "
            "Net income 10 (5) (20) "
            "in millions"
        ),
    )
    assert bundle.reference_table_row is not None
    s = bundle.reference_table_row.forecast_error
    lines = s.splitlines()
    assert len(lines) == 4
    assert lines[0].startswith("Revenue guidance in S-1: ")
    assert lines[1].startswith("Actual vs implied (first 3 years): ")
    assert lines[2].startswith("Profitability path: ")
    assert lines[3].startswith("Key miss/beat note: ")


def test_forecast_error_block_computes_actual_cagr_and_profit_year_from_10k() -> None:
    bundle = build_output_contract_bundle(
        company_name="TestCo",
        ticker="TCO",
        ipo_date=date(2021, 1, 1),
        parser_output={"business_model": "B2B software platform.", "offering_type": "primary"},
        scenario_output={"ipo_delivery_verdict": "mixed"},
        outcome_metrics=None,
        prediction_claims=[PredictionClaim(claim_id="c1", claim_type="growth", prediction_text="Growth.", source="SEC")],
        claim_checks=[ClaimCheck(claim_id="c1", status="supported")],
        patterns_flagged=[],
        comparable_tickers=[],
        s1_disclosure_checks=[
            ClaimCheck(
                claim_id="Revenue growth guidance present?",
                status="supported",
                evidence_quotes=["We expect revenue to grow at a 25% CAGR over the next several years."],
            ),
            ClaimCheck(
                claim_id="Profitability timeline mentioned?",
                status="supported",
                evidence_quotes=["We expect to achieve profitability by 2023."],
            ),
        ],
        post_ipo_10k=(
            "Years ended December 31, 2023, 2022 and 2021 "
            "Total revenue 300 200 100 "
            "Net income 10 (5) (20) "
            "in millions"
        ),
    )
    row = bundle.reference_table_row
    assert row is not None
    s = row.forecast_error
    # Actual CAGR from 100 -> 300 over 2 years is ~73.2%.
    assert "73.2% actual CAGR" in s
    assert "first annual profit 2023" in s


def test_forecast_error_block_falls_back_cleanly_without_guidance_or_10k() -> None:
    bundle = build_output_contract_bundle(
        company_name="TestCo",
        ticker="TCO",
        ipo_date=date(2021, 1, 1),
        parser_output={"business_model": "B2B software platform.", "offering_type": "primary"},
        scenario_output={"ipo_delivery_verdict": "mixed"},
        outcome_metrics=None,
        prediction_claims=[PredictionClaim(claim_id="c1", claim_type="growth", prediction_text="Growth.", source="SEC")],
        claim_checks=[ClaimCheck(claim_id="c1", status="supported")],
        patterns_flagged=[],
        comparable_tickers=[],
        s1_disclosure_checks=[],
        post_ipo_10k=None,
    )
    row = bundle.reference_table_row
    assert row is not None
    s = row.forecast_error
    assert "Revenue guidance in S-1: none / vague" in s
    assert "Actual vs implied (first 3 years): No explicit guidance in S-1" in s


def test_forecast_error_block_no_10k_with_guidance_uses_dataset_sentence() -> None:
    bundle = build_output_contract_bundle(
        company_name="TestCo",
        ticker="TCO",
        ipo_date=date(2021, 1, 1),
        parser_output={"business_model": "B2B software platform.", "offering_type": "primary"},
        scenario_output={"ipo_delivery_verdict": "mixed"},
        outcome_metrics=None,
        prediction_claims=[PredictionClaim(claim_id="c1", claim_type="growth", prediction_text="Growth.", source="SEC")],
        claim_checks=[ClaimCheck(claim_id="c1", status="supported")],
        patterns_flagged=[],
        comparable_tickers=[],
        s1_disclosure_checks=[
            ClaimCheck(
                claim_id="Revenue growth guidance present?",
                status="supported",
                evidence_quotes=["We expect revenue to grow at a 25% CAGR over the next several years."],
            ),
            ClaimCheck(
                claim_id="Profitability timeline mentioned?",
                status="missed",
                evidence_quotes=[],
            ),
        ],
        post_ipo_10k=None,
    )
    row = bundle.reference_table_row
    assert row is not None
    s = row.forecast_error
    assert "No comparable post-IPO revenue data available in dataset" in s
