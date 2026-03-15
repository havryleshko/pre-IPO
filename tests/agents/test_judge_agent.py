from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.judge_agent import JudgeAgent, JudgeAgentInput


def _minimal_scenario(name: str, probability: float = 33.33) -> dict:
    return {
        "probability": probability,
        "drivers": [f"driver for {name} (source: SEC)"],
        "key_risks": [f"risk for {name} (source: S-1)"],
        "price_targets": {"30_days": 10.0, "90_days": 12.0, "1_year": 15.0},
        "weighting_rationale": "Based on 45% revenue growth from SEC filing and news sentiment.",
        "rules_applied": [],
    }


def _minimal_recommendation(name: str) -> dict:
    para = " ".join(["word"] * 150)
    return {
        "recommended_positioning": "balanced market exposure",
        "conviction": "medium",
        "rationale": "Test rationale.",
        "risk_warning": "Test risk warning.",
        "client_paragraph": para,
    }


def _valid_analysis() -> dict:
    return {
        "company_name": "TestCo",
        "parser_output": {
            "financials": {
                "revenue": 100_000_000,
                "burn_rate_monthly": 5_000_000,
                "cash_runway_months": 18,
            },
            "risk_factors": [{"text": "Market risk (source: S-1)"}],
        },
        "scenario_output": {
            "scenarios": {
                "pessimistic": _minimal_scenario("pessimistic", 25.0),
                "realistic": _minimal_scenario("realistic", 50.0),
                "optimistic": _minimal_scenario("optimistic", 25.0),
            },
            "probability_sum_check": 100.0,
        },
        "recommendation_output": {
            "pre_ipo_beneficiary_funds": {
                "candidates": [{"fund_name": "Fund A", "evidence": ["parser funding history"]}],
                "methodology": "test",
            },
            "recommendations": {
                "pessimistic": _minimal_recommendation("pessimistic"),
                "realistic": _minimal_recommendation("realistic"),
                "optimistic": _minimal_recommendation("optimistic"),
            },
            "plain_english_summary": "TestCo shows balanced exposure across scenarios.",
        },
        "harvester_output": {
            "twitter_data": {"sentiment_score": {"positive": 0.3, "negative": 0.2, "neutral": 0.5}},
        },
    }


def test_validation_passes_clean_analysis() -> None:
    agent = JudgeAgent()
    issues = agent._collect_issues(_valid_analysis())
    assert len(issues) == 0


def test_validation_fails_missing_parser_output() -> None:
    agent = JudgeAgent()
    analysis = _valid_analysis()
    analysis["parser_output"] = None
    issues = agent._collect_issues(analysis)
    assert any(i.section == "Pipeline Outputs" for i in issues)


def test_validation_fails_incomplete_scenarios() -> None:
    agent = JudgeAgent()
    analysis = _valid_analysis()
    analysis["scenario_output"]["scenarios"]["optimistic"] = {}
    issues = agent._collect_issues(analysis)
    assert any(i.section == "Scenario Completeness" for i in issues)


def test_validation_fails_probability_sum_not_100() -> None:
    agent = JudgeAgent()
    analysis = _valid_analysis()
    analysis["scenario_output"]["probability_sum_check"] = 90.0
    issues = agent._collect_issues(analysis)
    assert any(i.section == "Probability Sum" for i in issues)


def test_validation_fails_missing_positioning() -> None:
    agent = JudgeAgent()
    analysis = _valid_analysis()
    analysis["recommendation_output"]["recommendations"]["pessimistic"]["recommended_positioning"] = ""
    issues = agent._collect_issues(analysis)
    assert any(i.section == "Post-IPO Positioning" for i in issues)


def test_validation_fails_missing_risk_warning() -> None:
    agent = JudgeAgent()
    analysis = _valid_analysis()
    analysis["recommendation_output"]["recommendations"]["realistic"]["risk_warning"] = ""
    issues = agent._collect_issues(analysis)
    assert any(i.section == "Risk Warnings" for i in issues)


def test_validation_fails_client_paragraph_over_500_words() -> None:
    agent = JudgeAgent()
    analysis = _valid_analysis()
    long_para = " ".join(["word"] * 501)
    analysis["recommendation_output"]["recommendations"]["optimistic"]["client_paragraph"] = long_para
    issues = agent._collect_issues(analysis)
    assert any(i.section == "Client Paragraph Length" for i in issues)


def test_validation_fails_empty_client_paragraph() -> None:
    agent = JudgeAgent()
    analysis = _valid_analysis()
    analysis["recommendation_output"]["recommendations"]["pessimistic"]["client_paragraph"] = ""
    issues = agent._collect_issues(analysis)
    assert any(i.section == "Client Paragraph Length" for i in issues)


def test_validation_fails_legal_jargon_in_summary() -> None:
    agent = JudgeAgent()
    analysis = _valid_analysis()
    analysis["recommendation_output"]["plain_english_summary"] = "The aforementioned terms notwithstanding."
    issues = agent._collect_issues(analysis)
    assert any(i.section == "Plain-English Summary" for i in issues)


@pytest.mark.asyncio
async def test_retry_passes_clears_issues() -> None:
    async def retry_ok(_aid: str, _sections: list[str]) -> bool:
        return True

    agent = JudgeAgent(retry_handler=retry_ok)
    bad = _valid_analysis()
    bad["parser_output"] = None
    good = _valid_analysis()
    with (
        patch("backend.agents.judge_agent.get_analysis_by_id", new_callable=AsyncMock, side_effect=[bad, good]) as get_mock,
        patch("backend.agents.judge_agent.save_judge_output", new_callable=AsyncMock) as save_mock,
        patch("backend.agents.judge_agent.set_flags_and_export_lock", new_callable=AsyncMock),
        patch("backend.agents.judge_agent.log_agent_run_start", new_callable=AsyncMock, return_value={"id": "run-1"}),
        patch("backend.agents.judge_agent.log_agent_run_completed", new_callable=AsyncMock),
    ):
        result = await agent.run(JudgeAgentInput(analysis_id="test-id"))
    assert result.analysis_id == "test-id"
    assert get_mock.call_count == 2
    output = save_mock.call_args.kwargs["output"]
    assert output["validation_passed"] is True
    assert output["export_locked"] is False


@pytest.mark.asyncio
async def test_retry_fails_issues_remain_export_locked() -> None:
    async def retry_fail(_aid: str, _sections: list[str]) -> bool:
        return False

    agent = JudgeAgent(retry_handler=retry_fail)
    analysis = _valid_analysis()
    analysis["parser_output"] = None
    with (
        patch("backend.agents.judge_agent.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis),
        patch("backend.agents.judge_agent.save_judge_output", new_callable=AsyncMock) as save_mock,
        patch("backend.agents.judge_agent.set_flags_and_export_lock", new_callable=AsyncMock) as lock_mock,
        patch("backend.agents.judge_agent.log_agent_run_start", new_callable=AsyncMock, return_value={"id": "run-1"}),
        patch("backend.agents.judge_agent.log_agent_run_completed", new_callable=AsyncMock),
    ):
        await agent.run(JudgeAgentInput(analysis_id="test-id"))
    call_args = save_mock.call_args
    output = call_args.kwargs["output"]
    assert output["validation_passed"] is False
    assert output["export_locked"] is True
    assert len(output["flags"]) > 0
    assert output["flags"][0]["retry_attempted"] is True
    assert output["flags"][0]["retry_passed"] is False
    lock_mock.assert_called_once()
    assert lock_mock.call_args.kwargs["export_locked"] is True


@pytest.mark.asyncio
async def test_validation_passes_export_unlocked() -> None:
    agent = JudgeAgent()
    with (
        patch("backend.agents.judge_agent.get_analysis_by_id", new_callable=AsyncMock, return_value=_valid_analysis()),
        patch("backend.agents.judge_agent.save_judge_output", new_callable=AsyncMock) as save_mock,
        patch("backend.agents.judge_agent.set_flags_and_export_lock", new_callable=AsyncMock) as lock_mock,
        patch("backend.agents.judge_agent.log_agent_run_start", new_callable=AsyncMock, return_value={"id": "run-1"}),
        patch("backend.agents.judge_agent.log_agent_run_completed", new_callable=AsyncMock),
    ):
        await agent.run(JudgeAgentInput(analysis_id="test-id"))
    output = save_mock.call_args.kwargs["output"]
    assert output["validation_passed"] is True
    assert output["export_locked"] is False
    assert len(output["flags"]) == 0
    assert lock_mock.call_args.kwargs["export_locked"] is False
