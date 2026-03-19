from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.recommendation_engine import (
    RecommendationEngine,
    RecommendationEngineInput,
)


def _minimal_scenario(name: str, probability: float = 33.33) -> dict:
    return {
        "probability": probability,
        "drivers": [f"driver for {name}"],
        "key_risks": [f"risk for {name}"],
        "price_targets": {"30_days": 10.0, "90_days": 12.0, "1_year": 15.0},
        "weighting_rationale": "test",
        "rules_applied": [],
    }


def _minimal_parser() -> dict:
    return {
        "financials": {"revenue": 100_000_000, "burn_rate_monthly": 5_000_000},
        "offering_type": "primary",
        "data_confidence": "medium",
    }


def _minimal_harvester() -> dict:
    return {}


def _scenario_output() -> dict:
    return {
        "scenarios": {
            "pessimistic": _minimal_scenario("pessimistic", 25.0),
            "realistic": _minimal_scenario("realistic", 50.0),
            "optimistic": _minimal_scenario("optimistic", 25.0),
        },
    }


EXPECTED_POSITIONINGS = frozenset({
    "capital preservation with low-volatility bias and staged entry",
    "selective growth exposure with strict risk limits",
    "growth-forward positioning with tactical upside participation",
    "balanced positioning tilted toward quality and liquidity",
    "balanced market exposure with incremental adds on confirmation",
})


def _word_count(text: str) -> int:
    return len(text.split())


def test_positioning_presence_all_scenarios() -> None:
    engine = RecommendationEngine()
    out = engine._build_recommendation_output(
        company_name="TestCo",
        scenario_output=_scenario_output(),
        parser_output=_minimal_parser(),
        harvester_output=_minimal_harvester(),
    )
    for scenario_name, reco in [
        ("pessimistic", out.recommendations.pessimistic),
        ("realistic", out.recommendations.realistic),
        ("optimistic", out.recommendations.optimistic),
    ]:
        assert reco.recommended_positioning, f"{scenario_name} missing positioning"
        assert reco.recommended_positioning in EXPECTED_POSITIONINGS, (
            f"{scenario_name} positioning '{reco.recommended_positioning}' not in expected set"
        )


def test_risk_warning_presence_all_scenarios() -> None:
    engine = RecommendationEngine()
    out = engine._build_recommendation_output(
        company_name="TestCo",
        scenario_output=_scenario_output(),
        parser_output=_minimal_parser(),
        harvester_output=_minimal_harvester(),
    )
    for scenario_name, reco in [
        ("pessimistic", out.recommendations.pessimistic),
        ("realistic", out.recommendations.realistic),
        ("optimistic", out.recommendations.optimistic),
    ]:
        assert reco.risk_warning, f"{scenario_name} missing risk_warning"
        assert len(reco.risk_warning.split(".")) >= 1


def test_concrete_investment_action_and_funds() -> None:
    engine = RecommendationEngine()
    harvester = {
        "sec_filings": [{"text": "Filing"}],
        "crunchbase_data": {"investors": ["Fidelity Growth Fund", "Sequoia Capital"]},
    }
    parser = {
        "financials": {"revenue": 100_000_000, "burn_rate_monthly": 5_000_000},
        "offering_type": "primary",
        "data_confidence": "high",
        "lockup_period_days": 180,
        "demand_signals": {"roadshow_sentiment": "strong demand"},
        "flagged_sections": [],
    }
    out = engine._build_recommendation_output(
        company_name="TestCo",
        scenario_output=_scenario_output(),
        parser_output=parser,
        harvester_output=harvester,
    )
    assert out.investment_action
    if out.decision == "buy":
        assert "Buy" in out.investment_action
    elif out.decision == "watch":
        assert out.investment_action.startswith("Watch")
    else:
        assert out.investment_action.startswith("Avoid")
    assert len(out.what_to_watch) >= 1
    assert any("lock-up" in w.lower() or "180" in w for w in out.what_to_watch)


def test_risk_warning_sanitizes_toc_noise() -> None:
    engine = RecommendationEngine()
    toc_noise_scenarios = {
        "pessimistic": _minimal_scenario("pessimistic", 25.0),
        "realistic": _minimal_scenario("realistic", 50.0),
        "optimistic": _minimal_scenario("optimistic", 25.0),
    }
    toc_noise_scenarios["realistic"]["key_risks"] = [
        "Investing in our Class A common stock involves risks. You should consider carefully.",
    ]
    out = engine._build_recommendation_output(
        company_name="TestCo",
        scenario_output={"scenarios": toc_noise_scenarios},
        parser_output=_minimal_parser(),
        harvester_output=_minimal_harvester(),
    )
    assert "investing in our" not in out.recommendations.realistic.risk_warning.lower()
    assert "market volatility" in out.recommendations.realistic.risk_warning.lower()


def test_client_paragraph_length_constraints() -> None:
    engine = RecommendationEngine()
    out = engine._build_recommendation_output(
        company_name="TestCo",
        scenario_output=_scenario_output(),
        parser_output=_minimal_parser(),
        harvester_output=_minimal_harvester(),
    )
    for scenario_name, reco in [
        ("pessimistic", out.recommendations.pessimistic),
        ("realistic", out.recommendations.realistic),
        ("optimistic", out.recommendations.optimistic),
    ]:
        wc = _word_count(reco.client_paragraph)
        assert 100 <= wc <= 500, (
            f"{scenario_name} client_paragraph has {wc} words, expected 100-500"
        )


def test_low_confidence_output_is_preliminary_and_not_synthetic() -> None:
    engine = RecommendationEngine()
    low_confidence_parser = {
        "financials": {"revenue": None, "burn_rate_monthly": None, "cash_runway_months": None},
        "offering_type": "primary",
        "data_confidence": "low",
        "flagged_sections": [
            {"section": "Financials", "reason": "Revenue missing", "verify_at": "SEC EDGAR"},
            {"section": "Use of Proceeds", "reason": "Missing", "verify_at": "SEC EDGAR"},
        ],
    }
    out = engine._build_recommendation_output(
        company_name="TestCo",
        scenario_output=_scenario_output(),
        parser_output=low_confidence_parser,
        harvester_output={"sources_active": ["sec_edgar", "news_api", "crunchbase"]},
    )

    assert out.plain_english_summary.lower().startswith("preliminary")
    assert "downside" not in out.plain_english_summary.lower()
    assert "base (" not in out.plain_english_summary.lower()
    assert out.pre_ipo_beneficiary_funds.candidates == []
    assert "preliminary" in out.recommendations.realistic.client_paragraph.lower()
    assert "30-day / 90-day / 1-year" not in out.recommendations.realistic.client_paragraph
    assert "low-confidence" in out.recommendations.realistic.rationale.lower()


@pytest.mark.asyncio
async def test_run_persists_output() -> None:
    engine = RecommendationEngine()
    analysis = {
        "company_name": "TestCo",
        "scenario_output": _scenario_output(),
        "parser_output": _minimal_parser(),
        "harvester_output": _minimal_harvester(),
    }
    with (
        patch("backend.agents.recommendation_engine.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis),
        patch("backend.agents.recommendation_engine.save_recommendation_output", new_callable=AsyncMock) as save_mock,
        patch("backend.agents.recommendation_engine.log_agent_run_start", new_callable=AsyncMock, return_value={"id": "run-1"}),
        patch("backend.agents.recommendation_engine.log_agent_run_completed", new_callable=AsyncMock),
    ):
        result = await engine.run(RecommendationEngineInput(analysis_id="test-id"))
    assert result.analysis_id == "test-id"
    saved = save_mock.call_args.kwargs["output"]
    assert "recommendations" in saved
    assert saved["recommendations"]["pessimistic"]["recommended_positioning"]
    assert saved["recommendations"]["pessimistic"]["risk_warning"]


def _scenario_output_with_probs(
    pessimistic_p: float,
    realistic_p: float,
    optimistic_p: float,
) -> dict:
    return {
        "scenarios": {
            "pessimistic": _minimal_scenario("pessimistic", pessimistic_p),
            "realistic": _minimal_scenario("realistic", realistic_p),
            "optimistic": _minimal_scenario("optimistic", optimistic_p),
        },
    }


def test_T254_low_confidence_downgrades_to_watch() -> None:
    engine = RecommendationEngine()
    low_confidence_parser = {
        "financials": {"revenue": None, "burn_rate_monthly": None, "cash_runway_months": None},
        "offering_type": "primary",
        "data_confidence": "low",
        "flagged_sections": [
            {"section": "Financials", "reason": "Revenue missing", "verify_at": "SEC EDGAR"},
            {"section": "Use of Proceeds", "reason": "Missing", "verify_at": "SEC EDGAR"},
        ],
    }
    optimistic_scenarios = _scenario_output_with_probs(10.0, 20.0, 70.0)
    out = engine._build_recommendation_output(
        company_name="TestCo",
        scenario_output=optimistic_scenarios,
        parser_output=low_confidence_parser,
        harvester_output={"sources_active": ["sec_edgar", "news_api", "crunchbase"]},
    )

    assert out.decision == "watch"
    assert out.decision_scope == "no_trade"
    assert out.entry_triggers == []
    assert len(out.watch_triggers) >= 1
    assert len(out.kill_criteria) >= 1


def test_T255_private_backer_cannot_be_buyable_vehicle() -> None:
    engine = RecommendationEngine()
    optimistic_scenarios = _scenario_output_with_probs(10.0, 20.0, 70.0)
    parser = {
        "financials": {"revenue": 100_000_000, "burn_rate_monthly": 5_000_000},
        "offering_type": "primary",
        "data_confidence": "high",
        "lockup_period_days": 180,
        "float_details": {"public_float": 70_000_000},
        "flagged_sections": [],
    }
    harvester = {
        "crunchbase_data": {"investors": ["Private Equity Group"]},
    }
    out = engine._build_recommendation_output(
        company_name="TestCo",
        scenario_output=optimistic_scenarios,
        parser_output=parser,
        harvester_output=harvester,
    )

    assert out.decision == "buy"
    assert out.funds_to_consider == []
    assert out.decision_scope != "pre_ipo_fund"


def test_private_ventures_name_is_excluded_from_funds_to_consider() -> None:
    engine = RecommendationEngine()
    optimistic_scenarios = _scenario_output_with_probs(10.0, 20.0, 70.0)
    parser = {
        "financials": {"revenue": 100_000_000, "burn_rate_monthly": 5_000_000},
        "offering_type": "primary",
        "data_confidence": "high",
        "lockup_period_days": 180,
        "float_details": {"public_float": 70_000_000},
        "flagged_sections": [],
    }
    harvester = {
        "crunchbase_data": {"investors": ["Sequoia Ventures"]},
    }
    out = engine._build_recommendation_output(
        company_name="TestCo",
        scenario_output=optimistic_scenarios,
        parser_output=parser,
        harvester_output=harvester,
    )

    assert "Sequoia Ventures" not in out.funds_to_consider
    assert out.decision_scope != "pre_ipo_fund"


def test_T256_no_tradability_cannot_emit_buy_pre_ipo_fund() -> None:
    engine = RecommendationEngine()
    optimistic_scenarios = _scenario_output_with_probs(10.0, 20.0, 70.0)
    parser = {
        "financials": {"revenue": 100_000_000, "burn_rate_monthly": 5_000_000},
        "offering_type": "primary",
        "data_confidence": "high",
        "lockup_period_days": 0,
        "float_details": {"public_float": 0},
        "flagged_sections": [],
    }
    harvester = {"crunchbase_data": {"investors": ["Fidelity Growth Fund"]}}
    out = engine._build_recommendation_output(
        company_name="TestCo",
        scenario_output=optimistic_scenarios,
        parser_output=parser,
        harvester_output=harvester,
    )

    assert not (out.decision == "buy" and out.decision_scope == "pre_ipo_fund")
    assert out.decision != "buy"
    assert out.decision_scope == "no_trade"


def test_T257_triggers_and_kill_criteria_present_when_required() -> None:
    engine = RecommendationEngine()
    optimistic_scenarios = _scenario_output_with_probs(10.0, 20.0, 70.0)
    parser_buy = {
        "financials": {"revenue": 100_000_000, "burn_rate_monthly": 5_000_000},
        "offering_type": "primary",
        "data_confidence": "high",
        "lockup_period_days": 180,
        "float_details": {"public_float": 70_000_000},
        "flagged_sections": [{"section": "Financials", "reason": "Revenue missing", "verify_at": "SEC EDGAR"}],
    }
    harvester_buy = {"crunchbase_data": {"investors": ["Fidelity Growth Fund"]}}
    out_buy = engine._build_recommendation_output(
        company_name="TestCo",
        scenario_output=optimistic_scenarios,
        parser_output=parser_buy,
        harvester_output=harvester_buy,
    )

    assert out_buy.decision == "buy"
    assert len(out_buy.entry_triggers) >= 1
    assert out_buy.watch_triggers == []
    assert len(out_buy.kill_criteria) >= 1

    low_confidence_parser = {
        "financials": {"revenue": None, "burn_rate_monthly": None, "cash_runway_months": None},
        "offering_type": "primary",
        "data_confidence": "low",
        "flagged_sections": [
            {"section": "Financials", "reason": "Revenue missing", "verify_at": "SEC EDGAR"},
            {"section": "Use of Proceeds", "reason": "Missing", "verify_at": "SEC EDGAR"},
        ],
    }
    out_watch = engine._build_recommendation_output(
        company_name="TestCo",
        scenario_output=optimistic_scenarios,
        parser_output=low_confidence_parser,
        harvester_output={"sources_active": ["sec_edgar"]},
    )

    assert out_watch.decision == "watch"
    assert out_watch.entry_triggers == []
    assert len(out_watch.watch_triggers) >= 1
    assert len(out_watch.kill_criteria) >= 1


def test_retail_summary_is_populated_with_simple_sections() -> None:
    engine = RecommendationEngine()
    out = engine._build_recommendation_output(
        company_name="TestCo",
        scenario_output=_scenario_output(),
        parser_output=_minimal_parser(),
        harvester_output=_minimal_harvester(),
    )

    assert out.retail_summary.verdict_line
    assert out.retail_summary.simple_conclusion
    assert len(out.retail_summary.what_i_see_now) >= 1
    assert len(out.retail_summary.why_that_matters) >= 1
    assert len(out.retail_summary.the_good) >= 1
    assert len(out.retail_summary.the_risk) >= 1
    assert len(out.retail_summary.key_data_points) >= 2
    assert out.retail_summary.action_ideas.conservative
    assert out.retail_summary.action_ideas.tactical
    assert out.retail_summary.action_ideas.risk_control


def test_investment_action_remains_consistent_with_watch_decision() -> None:
    engine = RecommendationEngine()
    low_confidence_parser = {
        "financials": {"revenue": None, "burn_rate_monthly": None, "cash_runway_months": None},
        "offering_type": "primary",
        "data_confidence": "low",
        "flagged_sections": [{"section": "Financials", "reason": "Revenue missing", "verify_at": "SEC EDGAR"}],
    }
    optimistic_scenarios = _scenario_output_with_probs(10.0, 20.0, 70.0)
    out = engine._build_recommendation_output(
        company_name="TestCo",
        scenario_output=optimistic_scenarios,
        parser_output=low_confidence_parser,
        harvester_output={"sources_active": ["sec_edgar"]},
    )

    assert out.decision == "watch"
    assert out.investment_action.lower().startswith("watch")
    assert out.retail_summary.is_preliminary is True
