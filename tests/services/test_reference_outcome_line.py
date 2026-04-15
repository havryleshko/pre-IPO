from __future__ import annotations

from datetime import date

from backend.models.single_agent_result import OutcomeMetrics
from backend.services.reference_output_contract import (
    format_long_term_outcome_line,
    outcome_metrics_has_core_price_signal,
)


def test_outcome_metrics_has_core_price_signal_true() -> None:
    om = OutcomeMetrics(ipo_price=10.0)
    assert outcome_metrics_has_core_price_signal(om) is True


def test_outcome_metrics_has_core_price_signal_false_when_only_dates() -> None:
    om = OutcomeMetrics(lock_up_cliff_date=date(2024, 1, 1))
    assert outcome_metrics_has_core_price_signal(om) is False


def test_format_long_term_outcome_line_deterministic() -> None:
    om = OutcomeMetrics(
        ipo_price=9.9,
        current_price=33.93,
        performance_since_ipo_pct=242.7273,
        peak_price=36.55,
        trough_price=1.69,
    )
    line = format_long_term_outcome_line(
        company_name="PL",
        outcome_metrics=om,
        delivery_verdict="mixed",
    )
    assert line == (
        "PL: IPO 9.90, current 33.93, since IPO +242.7%, peak 36.55, trough 1.69; delivery verdict mixed."
    )


def test_format_long_term_outcome_line_empty_core_falls_back() -> None:
    om = OutcomeMetrics(lock_up_cliff_date=date(2024, 1, 1))
    line = format_long_term_outcome_line(company_name="X", outcome_metrics=om, delivery_verdict=None)
    assert line == "X: post-IPO price performance unavailable."
