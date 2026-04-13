from __future__ import annotations

from datetime import date, datetime, timezone

from backend.models.single_agent_result import (
    CompanyProfile,
    IPOProjection,
    MonthBand,
    NumericBand,
    OutcomeMetrics,
    ReferenceTableRow,
    SingleAgentResult,
)
from backend.services.reference_output_contract import CanonicalReferenceRecord
from tests.evals.reference_output_scoring import score_reference_outputs
from tests.evals.reference_output_scoring import _has_text


def test_score_reference_outputs_scores_fields_and_projection() -> None:
    expected = [
        CanonicalReferenceRecord(
            company_name="Salesforce",
            ticker="CRM",
            company_ticker="Salesforce (CRM)",
            industry_region="CRM/Cloud Software (US)",
            ipo_date="23 Jun 2004",
            key_pre_ipo_claims="S-1/roadshow subscription SaaS model.",
            long_term_outcome="IPO $11; current $310.",
            forecast_error="Growth exceeded conservative models.",
            predicted_pattern="Pattern 2: Steady compounders with conservative narratives",
            predicted_pattern_id=2,
            source_tables=["table-4.csv"],
        )
    ]
    prediction = SingleAgentResult(
        company_name="Salesforce",
        generated_at=datetime.now(timezone.utc),
        company_profile=CompanyProfile(
            issuer_name="Salesforce",
            ticker="CRM",
            company_ticker="Salesforce (CRM)",
            industry_region="CRM/Cloud Software (US)",
            ipo_date=date(2004, 6, 23),
        ),
        outcome_metrics=OutcomeMetrics(
            ipo_price=11.0,
            trough_price=9.0,
            recovered_to_ipo_date=date(2005, 1, 1),
        ),
        ipo_projection=IPOProjection(
            predicted_pattern_id=2,
            likely_decline_band_pct=NumericBand(low=-25.0, high=-5.0, unit="percent"),
            likely_time_to_trough_months=MonthBand(low=1, high=12),
            rebound_probability_band=NumericBand(low=60.0, high=85.0, unit="percent"),
            likely_time_to_rebound_months=MonthBand(low=6, high=24),
        ),
        reference_table_row=ReferenceTableRow(
            company_ticker="Salesforce (CRM)",
            industry_region="CRM/Cloud Software (US)",
            ipo_date="23 Jun 2004",
            key_pre_ipo_claims="S-1/roadshow subscription SaaS model.",
            long_term_outcome="IPO $11; current $310.",
            forecast_error="Growth exceeded conservative models.",
            predicted_pattern="Pattern 2: Steady compounders with conservative narratives",
        ),
    )

    metrics = score_reference_outputs(expected, {"CRM": prediction})
    assert metrics.mandatory_field_coverage == 1.0
    assert metrics.pattern_accuracy == 1.0
    assert metrics.projection_field_coverage == 1.0
    assert metrics.decline_band_hit_rate == 1.0
    assert metrics.rebound_signal_accuracy == 1.0


def test_score_reference_outputs_treats_unavailable_as_missing() -> None:
    expected = [
        CanonicalReferenceRecord(
            company_name="Salesforce",
            ticker="CRM",
            company_ticker="Salesforce (CRM)",
            industry_region="CRM/Cloud Software (US)",
            ipo_date="23 Jun 2004",
            key_pre_ipo_claims="S-1/roadshow subscription SaaS model.",
            long_term_outcome="IPO $11; current $310.",
            forecast_error="Growth exceeded conservative models.",
            predicted_pattern="Pattern 2: Steady compounders with conservative narratives",
            predicted_pattern_id=2,
            source_tables=["table-4.csv"],
        )
    ]
    prediction = SingleAgentResult(
        company_name="Salesforce",
        generated_at=datetime.now(timezone.utc),
        company_profile=CompanyProfile(
            issuer_name="Salesforce",
            ticker="CRM",
            company_ticker="Salesforce (CRM)",
            industry_region="CRM/Cloud Software (US)",
            ipo_date=date(2004, 6, 23),
        ),
        outcome_metrics=OutcomeMetrics(
            ipo_price=11.0,
            trough_price=9.0,
            recovered_to_ipo_date=date(2005, 1, 1),
        ),
        ipo_projection=IPOProjection(
            predicted_pattern_id=2,
            likely_decline_band_pct=NumericBand(low=-25.0, high=-5.0, unit="percent"),
            likely_time_to_trough_months=MonthBand(low=1, high=12),
            rebound_probability_band=NumericBand(low=60.0, high=85.0, unit="percent"),
            likely_time_to_rebound_months=MonthBand(low=6, high=24),
        ),
        reference_table_row=ReferenceTableRow(
            company_ticker="Salesforce (CRM)",
            industry_region="unavailable",
            ipo_date="23 Jun 2004",
            key_pre_ipo_claims="S-1/roadshow subscription SaaS model.",
            long_term_outcome="IPO $11; current $310.",
            forecast_error="Growth exceeded conservative models.",
            predicted_pattern="Pattern 2: Steady compounders with conservative narratives",
        ),
    )

    metrics = score_reference_outputs(expected, {"CRM": prediction})
    assert metrics.mandatory_field_coverage == 6 / 7


def test_has_text_rejects_placeholder_with_punctuation() -> None:
    assert _has_text("unavailable.") is False
    assert _has_text("N/A.") is False
