from __future__ import annotations

from datetime import datetime, timezone

from tui.app import PreIPOTui
from tui.types import (
    OutcomeMetrics,
    RealizedOutcome,
    ReferenceTableRow,
    SingleAgentResult,
)


def test_map_result_prefers_realized_outcome_for_summary_and_forecast() -> None:
    app = PreIPOTui()
    result = SingleAgentResult(
        company_name="Co",
        generated_at=datetime.now(timezone.utc),
        outcome_metrics=OutcomeMetrics(ipo_price=1.0, current_price=2.0, performance_since_ipo_pct=100.0),
        reference_table_row=ReferenceTableRow(
            company_ticker="Co (C)",
            industry_region="X / Y",
            ipo_date="2020-01-01",
            key_pre_ipo_claims="claims",
            long_term_outcome="row summary stale",
            forecast_error="row forecast stale",
            predicted_pattern="Pattern 1",
        ),
        realized_outcome=RealizedOutcome(
            long_term_outcome="canonical summary",
            forecast_error="canonical forecast",
        ),
    )
    mapped = app._map_result_to_widget_data(result)
    assert mapped["long_term_outcome_summary"] == "canonical summary"
    assert mapped["forecast_error"] == "canonical forecast"
    assert mapped["outcome_data"]["ipo_price"] == 1.0


def test_map_result_leaves_outcome_table_empty_when_metrics_missing() -> None:
    app = PreIPOTui()
    result = SingleAgentResult(
        company_name="Co",
        generated_at=datetime.now(timezone.utc),
        outcome_metrics=None,
        reference_table_row=ReferenceTableRow(
            company_ticker="Co (C)",
            industry_region="X / Y",
            ipo_date="2020-01-01",
            key_pre_ipo_claims="claims",
            long_term_outcome="Co: IPO 10.00, current 20.00, since IPO +100.0%, peak 25.00, trough 8.00; delivery verdict mixed.",
            forecast_error="mixed",
            predicted_pattern="Pattern 1",
        ),
        realized_outcome=RealizedOutcome(
            long_term_outcome="Co: IPO 10.00, current 20.00, since IPO +100.0%, peak 25.00, trough 8.00; delivery verdict mixed.",
            forecast_error="mixed",
        ),
    )
    mapped = app._map_result_to_widget_data(result)
    assert mapped["outcome_data"] == {}
