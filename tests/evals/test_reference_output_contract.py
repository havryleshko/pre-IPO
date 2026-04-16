from __future__ import annotations

from datetime import date

from backend.agents.prospectus_parser import (
    S1_DISCLOSURE_CHECKLIST_CUSTOMER_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_MARKET_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_PROFIT_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_PROJECTION_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_REVENUE_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_RISK_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_SPARSE_CLAIM_ID,
)
from backend.models.single_agent_result import ClaimCheck, OutcomeMetrics, PredictionClaim
from backend.services.reference_output_contract import (
    _parse_company_ticker,
    build_output_contract_bundle,
    load_canonical_reference_dataset,
    lookup_reference_record,
)


def test_load_canonical_reference_dataset_reconciles_duplicates() -> None:
    records = load_canonical_reference_dataset()
    assert records
    robinhood = next(record for record in records if record.ticker == "HOOD")
    assert robinhood.company_ticker.startswith("Robinhood")
    assert robinhood.predicted_pattern
    assert robinhood.source_tables
    assert "table-3.csv" in robinhood.source_tables
    assert "table-4.csv" in robinhood.source_tables


def test_lookup_reference_record_by_ticker() -> None:
    record = lookup_reference_record(company_name="Salesforce", ticker="CRM")
    assert record is not None
    assert record.ticker == "CRM"
    assert "Steady compounders" in record.predicted_pattern


def test_parse_company_ticker_extracts_first_token_from_messy_parenthetical() -> None:
    name, ticker = _parse_company_ticker("Block (SQ; formerly Square)")
    assert name == "Block"
    assert ticker == "SQ"

    name, ticker = _parse_company_ticker("Twitter (TWTR; now X, delisted)")
    assert name == "Twitter"
    assert ticker == "TWTR"

    name, ticker = _parse_company_ticker("Uber (NYSE: UBER)")
    assert name == "Uber"
    assert ticker == "UBER"


def test_lookup_reference_record_matches_messy_reference_rows_by_ticker() -> None:
    block = lookup_reference_record(company_name="Block", ticker="SQ")
    assert block is not None
    assert block.ticker == "SQ"

    twitter = lookup_reference_record(company_name="Twitter", ticker="TWTR")
    assert twitter is not None
    assert twitter.ticker == "TWTR"


def test_build_output_contract_bundle_uses_reference_match() -> None:
    bundle = build_output_contract_bundle(
        company_name="Salesforce",
        ticker="CRM",
        ipo_date=date(2004, 6, 23),
        parser_output={"offering_type": "primary"},
        scenario_output={"ipo_delivery_verdict": "delivered"},
        outcome_metrics=OutcomeMetrics(ipo_price=11.0, current_price=310.0, performance_since_ipo_pct=2700.0),
        prediction_claims=[PredictionClaim(claim_id="c1", claim_type="growth", prediction_text="Growth.", source="SEC")],
        claim_checks=[ClaimCheck(claim_id="c1", status="supported")],
        patterns_flagged=[],
        comparable_tickers=["TEAM"],
    )
    assert bundle.reference_table_row.company_ticker.startswith("Salesforce")
    assert bundle.reference_table_row.industry_region
    assert "Pattern 2" in bundle.reference_table_row.predicted_pattern
    assert bundle.pattern_classification.primary_pattern_id == 2
    assert bundle.pattern_classification.source == "reference_exact"
    assert bundle.reference_table_row.long_term_outcome.startswith("Salesforce:")
    assert "IPO 11.00" in bundle.reference_table_row.long_term_outcome
    assert "current 310.00" in bundle.reference_table_row.long_term_outcome
    assert "delivery verdict delivered" in bundle.reference_table_row.long_term_outcome
    assert bundle.realized_outcome.long_term_outcome == bundle.reference_table_row.long_term_outcome


def test_build_output_contract_reference_match_without_core_metrics_uses_csv_outcome() -> None:
    bundle = build_output_contract_bundle(
        company_name="Salesforce",
        ticker="CRM",
        ipo_date=date(2004, 6, 23),
        parser_output={"offering_type": "primary"},
        scenario_output={"ipo_delivery_verdict": "delivered"},
        outcome_metrics=None,
        prediction_claims=[PredictionClaim(claim_id="c1", claim_type="growth", prediction_text="Growth.", source="SEC")],
        claim_checks=[ClaimCheck(claim_id="c1", status="supported")],
        patterns_flagged=[],
        comparable_tickers=["TEAM"],
    )
    record = lookup_reference_record(company_name="Salesforce", ticker="CRM")
    assert record is not None
    assert bundle.reference_table_row.long_term_outcome == record.long_term_outcome


def test_build_output_contract_bundle_with_disclosure_checks_includes_management_tone() -> None:
    disclosure = [
        ClaimCheck(claim_id=S1_DISCLOSURE_CHECKLIST_REVENUE_CLAIM_ID, status="supported", evidence_quotes=["We expect rapid revenue growth."]),
        ClaimCheck(claim_id=S1_DISCLOSURE_CHECKLIST_PROFIT_CLAIM_ID, status="missed", evidence_quotes=[]),
        ClaimCheck(claim_id=S1_DISCLOSURE_CHECKLIST_CUSTOMER_CLAIM_ID, status="missed", evidence_quotes=[]),
        ClaimCheck(claim_id=S1_DISCLOSURE_CHECKLIST_MARKET_CLAIM_ID, status="missed", evidence_quotes=[]),
        ClaimCheck(claim_id=S1_DISCLOSURE_CHECKLIST_RISK_CLAIM_ID, status="missed", evidence_quotes=[]),
        ClaimCheck(claim_id=S1_DISCLOSURE_CHECKLIST_PROJECTION_CLAIM_ID, status="missed", evidence_quotes=[]),
        ClaimCheck(claim_id=S1_DISCLOSURE_CHECKLIST_SPARSE_CLAIM_ID, status="missed", evidence_quotes=[]),
    ]
    bundle = build_output_contract_bundle(
        company_name="UnknownCo",
        ticker="UNKN",
        ipo_date=date(2021, 7, 1),
        parser_output={"business_model": "B2B software platform.", "offering_type": "primary"},
        scenario_output={"ipo_delivery_verdict": "mixed"},
        outcome_metrics=OutcomeMetrics(ipo_price=20.0, current_price=10.0, performance_since_ipo_pct=-50.0),
        prediction_claims=[PredictionClaim(claim_id="c1", claim_type="growth", prediction_text="Rapid growth expected.", source="SEC")],
        claim_checks=[ClaimCheck(claim_id="c1", status="missed")],
        patterns_flagged=[],
        comparable_tickers=[],
        s1_disclosure_checks=disclosure,
    )
    assert bundle.pre_ipo_thesis is not None
    assert bundle.pre_ipo_thesis.key_pre_ipo_claims
    assert bundle.pre_ipo_thesis.key_pre_ipo_claims[0].startswith("Management tone:")
    assert "Management tone:" in bundle.reference_table_row.key_pre_ipo_claims


def test_build_output_contract_bundle_falls_back_to_heuristics() -> None:
    bundle = build_output_contract_bundle(
        company_name="UnknownCo",
        ticker="UNKN",
        ipo_date=date(2021, 7, 1),
        parser_output={
            "business_model": "High-growth consumer platform business.",
            "offering_type": "primary",
        },
        scenario_output={"ipo_delivery_verdict": "mixed"},
        outcome_metrics=OutcomeMetrics(ipo_price=20.0, current_price=10.0, performance_since_ipo_pct=-50.0),
        prediction_claims=[PredictionClaim(claim_id="c1", claim_type="growth", prediction_text="Rapid growth expected.", source="SEC")],
        claim_checks=[ClaimCheck(claim_id="c1", status="missed")],
        patterns_flagged=[],
        comparable_tickers=[],
    )
    assert bundle.reference_table_row.company_ticker == "UnknownCo (UNKN)"
    assert bundle.reference_table_row.key_pre_ipo_claims
    assert bundle.reference_table_row.forecast_error
    assert bundle.pattern_classification.primary_pattern_id is not None


def test_build_output_contract_bundle_uses_yahoo_industry_region_for_non_reference() -> None:
    bundle = build_output_contract_bundle(
        company_name="UnknownCo",
        ticker="UNKN",
        ipo_date=date(2021, 7, 1),
        parser_output={"business_model": "B2B software", "offering_type": "primary"},
        scenario_output={"ipo_delivery_verdict": "mixed"},
        outcome_metrics=OutcomeMetrics(ipo_price=20.0, current_price=10.0, performance_since_ipo_pct=-50.0),
        prediction_claims=[PredictionClaim(claim_id="c1", claim_type="growth", prediction_text="Rapid growth expected.", source="SEC")],
        claim_checks=[ClaimCheck(claim_id="c1", status="missed")],
        patterns_flagged=[],
        comparable_tickers=[],
        yahoo_finance_data={"industry": "Application Software", "country": "United States"},
    )
    assert bundle.company_profile.industry_region == "Application Software / United States"
    assert bundle.reference_table_row.industry_region == "Application Software / United States"
