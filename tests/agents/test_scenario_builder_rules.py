from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.scenario_builder import ScenarioBuilder, ScenarioBuilderInput


def _minimal_parser() -> dict:
    return {
        "financials": {"revenue": 100.0, "burn_rate_monthly": 0.0},
        "float_details": {"public_float": 50.0, "total_shares_offered": 100.0},
        "demand_signals": {"anchor_investors": [], "institutional_interest": "unknown", "roadshow_sentiment": ""},
        "risk_factors": [],
        "lockup_period_days": 180,
        "insider_selling_percentage": None,
        "offering_type": "primary",
        "data_confidence": "medium",
    }


def _minimal_harvester() -> dict:
    return {"yahoo_finance_data": {"sector_90d_performance": 0.0}, "fred_data": {}, "twitter_data": {}}


def test_probability_weightings_sum_to_100() -> None:
    builder = ScenarioBuilder()
    out = builder._build_output(
        company_name="TestCo",
        complexity_tier="standard",
        parser_output=_minimal_parser(),
        harvester_output=_minimal_harvester(),
    )
    assert out.probability_sum_check == 100.0
    total = (
        out.scenarios.pessimistic.probability
        + out.scenarios.realistic.probability
        + out.scenarios.optimistic.probability
    )
    assert abs(total - 100.0) < 0.01


def test_high_burn_no_revenue_triggers_pessimistic() -> None:
    builder = ScenarioBuilder()
    parser = _minimal_parser()
    parser["financials"] = {"revenue": None, "burn_rate_monthly": 50_000_000}
    out = builder._build_output(
        company_name="TestCo",
        complexity_tier="standard",
        parser_output=parser,
        harvester_output=_minimal_harvester(),
    )
    assert "high_burn_no_revenue" in out.scenarios.pessimistic.rules_applied
    assert out.scenarios.pessimistic.probability > 30.0


def test_insider_selling_ge_30_triggers_pessimistic() -> None:
    builder = ScenarioBuilder()
    parser = _minimal_parser()
    parser["insider_selling_percentage"] = 35.0
    out = builder._build_output(
        company_name="TestCo",
        complexity_tier="standard",
        parser_output=parser,
        harvester_output=_minimal_harvester(),
    )
    assert "insider_selling_ge_30" in out.scenarios.pessimistic.rules_applied
    assert out.scenarios.pessimistic.probability > 30.0


def test_insider_selling_exactly_30_triggers() -> None:
    builder = ScenarioBuilder()
    parser = _minimal_parser()
    parser["insider_selling_percentage"] = 30.0
    out = builder._build_output(
        company_name="TestCo",
        complexity_tier="standard",
        parser_output=parser,
        harvester_output=_minimal_harvester(),
    )
    assert "insider_selling_ge_30" in out.scenarios.pessimistic.rules_applied


def test_anchor_investors_triggers_optimistic() -> None:
    builder = ScenarioBuilder()
    parser = _minimal_parser()
    parser["demand_signals"] = {
        "anchor_investors": ["Sequoia", "a16z"],
        "institutional_interest": "unknown",
        "roadshow_sentiment": "",
    }
    out = builder._build_output(
        company_name="TestCo",
        complexity_tier="standard",
        parser_output=parser,
        harvester_output=_minimal_harvester(),
    )
    assert "anchor_investors_present" in out.scenarios.optimistic.rules_applied
    assert out.scenarios.optimistic.probability > 30.0


def test_hot_sector_triggers_optimistic() -> None:
    builder = ScenarioBuilder()
    harvester = _minimal_harvester()
    harvester["yahoo_finance_data"] = {"sector_90d_performance": 15.0}
    out = builder._build_output(
        company_name="TestCo",
        complexity_tier="standard",
        parser_output=_minimal_parser(),
        harvester_output=harvester,
    )
    assert "hot_sector_positive_90d" in out.scenarios.optimistic.rules_applied


def test_primary_offering_triggers_optimistic() -> None:
    builder = ScenarioBuilder()
    parser = _minimal_parser()
    parser["offering_type"] = "primary"
    out = builder._build_output(
        company_name="TestCo",
        complexity_tier="standard",
        parser_output=parser,
        harvester_output=_minimal_harvester(),
    )
    assert "primary_offering_only" in out.scenarios.optimistic.rules_applied


def test_high_institutional_interest_triggers_optimistic() -> None:
    builder = ScenarioBuilder()
    parser = _minimal_parser()
    parser["demand_signals"] = {
        "anchor_investors": [],
        "institutional_interest": "high",
        "roadshow_sentiment": "",
    }
    out = builder._build_output(
        company_name="TestCo",
        complexity_tier="standard",
        parser_output=parser,
        harvester_output=_minimal_harvester(),
    )
    assert "high_institutional_interest" in out.scenarios.optimistic.rules_applied


def test_llm_adjustment_capped_at_15() -> None:
    builder = ScenarioBuilder()
    adj, _ = builder._llm_style_adjustment(
        {"data_confidence": "high", "risk_factors": [], "demand_signals": {"roadshow_sentiment": "strong oversubscribed"}},
        {"fred_data": {"market_conditions": "accommodative"}, "twitter_data": {"sentiment_score": {"positive": 0.9, "negative": 0.0, "neutral": 0.1}}},
    )
    assert -15.0 <= adj <= 15.0
    adj_neg, _ = builder._llm_style_adjustment(
        {"data_confidence": "low", "risk_factors": ["r"] * 10, "demand_signals": {"roadshow_sentiment": "weak soft demand"}},
        {"fred_data": {"market_conditions": "restrictive tightening"}, "twitter_data": {"sentiment_score": {"positive": 0.0, "negative": 0.9, "neutral": 0.1}}},
    )
    assert adj_neg >= -15.0


def test_normalize_weights_sums_to_100() -> None:
    builder = ScenarioBuilder()
    weights = {"pessimistic": 25.0, "realistic": 50.0, "optimistic": 25.0}
    normalized = builder._normalize_weights(weights)
    total = normalized["pessimistic"] + normalized["realistic"] + normalized["optimistic"]
    assert abs(total - 100.0) < 0.01


@pytest.mark.asyncio
async def test_run_persists_output() -> None:
    builder = ScenarioBuilder()
    analysis = {
        "company_name": "TestCo",
        "complexity_tier": "standard",
        "parser_output": _minimal_parser(),
        "harvester_output": _minimal_harvester(),
    }
    with (
        patch("backend.agents.scenario_builder.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis),
        patch("backend.agents.scenario_builder.save_scenario_output", new_callable=AsyncMock) as save_mock,
        patch("backend.agents.scenario_builder.log_agent_run_start", new_callable=AsyncMock, return_value={"id": "run-1"}),
        patch("backend.agents.scenario_builder.log_agent_run_completed", new_callable=AsyncMock),
    ):
        result = await builder.run(ScenarioBuilderInput(analysis_id="test-id"))
    assert result.analysis_id == "test-id"
    saved = save_mock.call_args.kwargs["output"]
    assert saved["probability_sum_check"] == 100.0
    total = (
        saved["scenarios"]["pessimistic"]["probability"]
        + saved["scenarios"]["realistic"]["probability"]
        + saved["scenarios"]["optimistic"]["probability"]
    )
    assert abs(total - 100.0) < 0.01
