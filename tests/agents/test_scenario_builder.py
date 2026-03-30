from datetime import date

import pytest

from backend.agents.scenario_builder import ScenarioBuilder
from backend.models.scenario_output import DeliveryEvidence, PricePerformance


def test_compute_delivery_score_delivered() -> None:
    builder = ScenarioBuilder()
    evidence = [
        DeliveryEvidence(claim="revenue S-1 projection: 100", actual="revenue 10-K actual: 100", verdict="met"),
        DeliveryEvidence(claim="burn_rate S-1 projection: 50", actual="burn_rate 10-K actual: 55", verdict="exceeded"),
    ]
    score, verdict = builder.compute_delivery_score(evidence, None)
    assert verdict == "delivered"
    assert score >= 65.0


def test_compute_delivery_score_underdelivered() -> None:
    builder = ScenarioBuilder()
    evidence = [
        DeliveryEvidence(claim="revenue S-1 projection: 100", actual="revenue 10-K actual: 50", verdict="missed"),
        DeliveryEvidence(claim="burn_rate S-1 projection: 40", actual="burn_rate 10-K actual: 80", verdict="missed"),
    ]
    perf = PricePerformance(performance_since_ipo_pct=-25.0)
    score, verdict = builder.compute_delivery_score(evidence, perf)
    assert verdict == "underdelivered"
    assert score <= 40.0


def test_compute_delivery_score_mixed() -> None:
    builder = ScenarioBuilder()
    evidence = [
        DeliveryEvidence(claim="revenue S-1 projection: 100", actual="revenue 10-K actual: 100", verdict="met"),
        DeliveryEvidence(claim="burn_rate S-1 projection: 40", actual="burn_rate 10-K actual: 80", verdict="missed"),
    ]
    score, verdict = builder.compute_delivery_score(evidence, None)
    assert verdict == "mixed"
    assert 40.0 < score < 65.0


def test_detect_ipo_patterns_lockup_cliff_stress() -> None:
    builder = ScenarioBuilder()
    parser_output = {"insider_selling_percentage": 32.0, "demand_signals": {"anchor_investors": []}}
    pp = PricePerformance(
        current_price=70.0,
        price_at_lock_up_cliff=100.0,
    )
    flags = builder.detect_ipo_patterns(parser_output, pp, delivery_evidence=[])
    signals = {f.signal for f in flags}
    assert "insider_selling_lockup_cliff_pressure" in signals


def test_detect_ipo_patterns_burn_miss_uses_evidence() -> None:
    builder = ScenarioBuilder()
    parser_output: dict = {"demand_signals": {"anchor_investors": []}}
    ev = [
        DeliveryEvidence(claim="burn_rate S-1 projection: 10", actual="burn_rate 10-K actual: 20", verdict="missed"),
    ]
    flags = builder.detect_ipo_patterns(parser_output, None, delivery_evidence=ev)
    assert any(f.signal == "burn_rate_forecast_inaccuracy" for f in flags)


def test_forward_targets_scale_to_current_price_baseline() -> None:
    builder = ScenarioBuilder()
    harvester = {
        "yahoo_finance_data": {"sector_90d_performance": 0.0},
        "ipo_price_history": {"current_price": 50.0},
    }
    parser_output = {
        "financials": {"revenue": 100.0, "burn_rate_monthly": 0.0},
        "float_details": {"public_float": 50.0, "total_shares_offered": 100.0},
        "demand_signals": {"anchor_investors": [], "institutional_interest": "unknown", "roadshow_sentiment": ""},
        "risk_factors": [],
        "lockup_period_days": 180,
        "insider_selling_percentage": None,
        "offering_type": "primary",
        "data_confidence": "medium",
    }
    out = builder._build_output(
        company_name="Co",
        complexity_tier="standard",
        parser_output=parser_output,
        harvester_output=harvester,
    )
    p = out.scenarios.pessimistic.price_targets
    r = out.scenarios.realistic.price_targets
    o = out.scenarios.optimistic.price_targets
    for t in (p, r, o):
        assert t.days_30 > 0 and t.days_90 > 0 and t.year_1 > 0
    assert p.year_1 <= r.year_1 <= o.year_1
    assert abs(r.year_1 - 53.0) < 0.01


@pytest.mark.parametrize(
    "lock_raw",
    [date(2024, 3, 15), "2024-03-15"],
)
def test_price_performance_parses_lock_up_date(lock_raw: date | str) -> None:
    builder = ScenarioBuilder()
    h = {"ipo_price_history": {"current_price": 1.0, "lock_up_cliff_date": lock_raw}}
    pp = builder._price_performance_from_harvester(h)
    assert pp is not None
    assert pp.lock_up_cliff_date == date(2024, 3, 15)
