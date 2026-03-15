from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from backend.agents.complexity_classifier import (
    ComplexityClassifierInput,
    classify_complexity,
)
from backend.agents.data_harvester import DataHarvester, DataHarvesterInput
from backend.agents.judge_agent import JudgeAgent, JudgeAgentInput
from backend.agents.prospectus_parser import ProspectusParser, ProspectusParserInput
from backend.agents.recommendation_engine import (
    RecommendationEngine,
    RecommendationEngineInput,
)
from backend.agents.scenario_builder import ScenarioBuilder, ScenarioBuilderInput
from backend.models.harvester_output import (
    CrunchbaseData,
    FredData,
    SecFiling,
    TwitterData,
    TwitterSentimentScore,
    YahooFinanceData,
)
from backend.services.resume_service import (
    ResumeServiceInput,
    resume_from_last_completed_agent,
)

SAMPLE_S1 = """
Total revenue for the year was $1,500 million. Cash used in operating activities was $50 million per month.
Cash runway 18 months. The 180 days lock-up period applies to insiders.
Total shares offered 100,000,000. Public float 70,000,000.
"""


async def _mock_sec_edgar(company_name: str) -> list[SecFiling]:
    return [SecFiling(url="https://sec.gov/1", text=SAMPLE_S1, filing_type="S-1")]


async def _mock_rss(company_name: str) -> list:
    return []


async def _mock_news_api(company_name: str) -> list:
    return []


async def _mock_crunchbase(company_name: str) -> CrunchbaseData:
    return CrunchbaseData(investors=["Sequoia"])


async def _mock_yahoo(company_name: str) -> YahooFinanceData:
    return YahooFinanceData(sector_90d_performance=0.0)


async def _mock_fred() -> FredData:
    return FredData()


async def _mock_twitter(company_name: str) -> TwitterData:
    return TwitterData(sentiment_score=TwitterSentimentScore(positive=0.3, negative=0.2, neutral=0.5))


def _make_store(analysis_id: str, company_name: str = "TestCo") -> dict:
    return {
        "id": analysis_id,
        "company_name": company_name,
        "complexity_tier": "standard",
        "status": "pending",
        "last_completed_agent": None,
        "harvester_output": None,
        "parser_output": None,
        "scenario_output": None,
        "recommendation_output": None,
        "judge_output": None,
        "flags": None,
        "export_locked": True,
        "created_at": datetime.now(timezone.utc),
    }


@pytest.mark.asyncio
async def test_full_pipeline_happy_path_produces_three_scenarios() -> None:
    analysis_id = str(uuid4())
    store = _make_store(analysis_id)

    async def get_analysis(aid: str):
        return dict(store) if aid == analysis_id else None

    async def save_harvester(**kw: object) -> str:
        if kw.get("analysis_id") == analysis_id:
            store["harvester_output"] = kw.get("output")
        return ""

    async def save_parser(**kw: object) -> str:
        if kw.get("analysis_id") == analysis_id:
            store["parser_output"] = kw.get("output")
        return ""

    async def save_scenario(**kw: object) -> str:
        if kw.get("analysis_id") == analysis_id:
            store["scenario_output"] = kw.get("output")
        return ""

    async def save_recommendation(**kw: object) -> str:
        if kw.get("analysis_id") == analysis_id:
            store["recommendation_output"] = kw.get("output")
        return ""

    async def save_judge(**kw: object) -> str:
        if kw.get("analysis_id") == analysis_id:
            store["judge_output"] = kw.get("output")
        return ""

    expected_id = analysis_id

    async def update_status(*args: object, **kwargs: object) -> str:
        aid = kwargs.get("analysis_id", args[0] if args else "")
        if aid == expected_id:
            store["status"] = str(kwargs.get("status", args[1] if len(args) > 1 else ""))
            lca = kwargs.get("last_completed_agent")
            if lca is not None:
                store["last_completed_agent"] = lca
        return ""

    async def set_flags(**kw: object) -> str:
        if kw.get("analysis_id") == analysis_id:
            store["flags"] = kw.get("flags")
            store["export_locked"] = kw.get("export_locked", True)
        return ""

    dh = DataHarvester(
        sec_edgar=_mock_sec_edgar,
        rss_feeds=_mock_rss,
        news_api=_mock_news_api,
        crunchbase=_mock_crunchbase,
        yahoo_finance=_mock_yahoo,
        fred=_mock_fred,
        twitter=_mock_twitter,
    )
    pp = ProspectusParser()
    sb = ScenarioBuilder()
    re = RecommendationEngine()
    judge = JudgeAgent()

    async def dh_executor(aid: str) -> None:
        classifier = classify_complexity(ComplexityClassifierInput(company_name=store["company_name"]))
        await dh.run(
            DataHarvesterInput(
                analysis_id=aid,
                company_name=store["company_name"],
                complexity_tier=classifier.complexity_tier,
                active_sources=classifier.active_sources,
            )
        )

    async def pp_executor(aid: str) -> None:
        await pp.run(ProspectusParserInput(analysis_id=aid))

    async def sb_executor(aid: str) -> None:
        await sb.run(ScenarioBuilderInput(analysis_id=aid))

    async def re_executor(aid: str) -> None:
        await re.run(RecommendationEngineInput(analysis_id=aid))

    async def judge_executor(aid: str) -> None:
        await judge.run(JudgeAgentInput(analysis_id=aid))

    executors = {
        "data_harvester": dh_executor,
        "prospectus_parser": pp_executor,
        "scenario_builder": sb_executor,
        "recommendation_engine": re_executor,
        "judge_agent": judge_executor,
    }

    patches = [
        ("backend.database.queries.get_analysis_by_id", get_analysis),
        ("backend.database.queries.save_harvester_output", save_harvester),
        ("backend.database.queries.save_parser_output", save_parser),
        ("backend.database.queries.save_scenario_output", save_scenario),
        ("backend.database.queries.save_recommendation_output", save_recommendation),
        ("backend.database.queries.save_judge_output", save_judge),
        ("backend.database.queries.update_analysis_status", update_status),
        ("backend.database.queries.set_flags_and_export_lock", set_flags),
        ("backend.services.resume_service.get_analysis_by_id", get_analysis),
        ("backend.services.retry_service.get_analysis_by_id", get_analysis),
        ("backend.agents.prospectus_parser.get_analysis_by_id", get_analysis),
        ("backend.agents.scenario_builder.get_analysis_by_id", get_analysis),
        ("backend.agents.recommendation_engine.get_analysis_by_id", get_analysis),
        ("backend.agents.judge_agent.get_analysis_by_id", get_analysis),
        ("backend.agents.data_harvester.save_harvester_output", save_harvester),
        ("backend.agents.prospectus_parser.save_parser_output", save_parser),
        ("backend.agents.scenario_builder.save_scenario_output", save_scenario),
        ("backend.agents.recommendation_engine.save_recommendation_output", save_recommendation),
        ("backend.agents.judge_agent.save_judge_output", save_judge),
        ("backend.agents.judge_agent.set_flags_and_export_lock", set_flags),
        ("backend.services.analysis_status_service.update_analysis_status", update_status),
    ]
    log_return = {"id": "1"}
    with ExitStack() as stack:
        for target, side_effect in patches:
            stack.enter_context(
                patch(target, new_callable=AsyncMock, side_effect=side_effect)
            )
        for mod in ["data_harvester", "prospectus_parser", "scenario_builder", "recommendation_engine", "judge_agent"]:
            stack.enter_context(
                patch(f"backend.agents.{mod}.log_agent_run_start", new_callable=AsyncMock, return_value=log_return)
            )
            stack.enter_context(
                patch(f"backend.agents.{mod}.log_agent_run_completed", new_callable=AsyncMock)
            )
        result = await resume_from_last_completed_agent(
            ResumeServiceInput(analysis_id=analysis_id),
            executors=executors,
        )

    assert result.completed is True
    assert result.analysis_id == analysis_id
    scenario_output = store.get("scenario_output")
    assert scenario_output is not None
    scenarios = scenario_output.get("scenarios")
    assert isinstance(scenarios, dict)
    assert "pessimistic" in scenarios
    assert "realistic" in scenarios
    assert "optimistic" in scenarios
