from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from backend.agents.complexity_classifier import (
    ComplexityClassifierInput,
    classify_complexity,
)
from backend.agents.prospectus_parser import ProspectusParser, ProspectusParserInput
from backend.agents.investor_brief_synthesizer import InvestorBriefSynthesizer, InvestorBriefSynthesizerInput
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
from backend.services import pipeline_runner

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
        "investor_brief": None,
        "created_at": datetime.now(timezone.utc),
    }


@pytest.mark.asyncio
async def test_full_pipeline_happy_path_produces_three_scenarios() -> None:
    import os
    os.environ["OPENAI_API_KEY"] = "test"
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

    async def save_investor_brief(**kw: object) -> str:
        if kw.get("analysis_id") == analysis_id:
            store["investor_brief"] = kw.get("output")
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

    pp = ProspectusParser()
    sb = ScenarioBuilder()
    class MockInvestorBriefSynthesizer:
        async def run(self, payload):
            await save_investor_brief(
                analysis_id=payload.analysis_id,
                output={
                    "company_name": "TestCo",
                    "sector_theme": "Tech",
                    "primary_instrument": {
                        "name": "Tech ETF",
                        "ticker": "TECH",
                        "rationale_one_liner": "Good"
                    },
                    "alternates": [],
                    "overview_markdown": "Test overview",
                    "references": [],
                    "disclaimer_short": "No advice."
                }
            )

    ibs = MockInvestorBriefSynthesizer()
    

    async def pp_executor(aid: str) -> None:
        await pp.run(ProspectusParserInput(analysis_id=aid))

    async def sb_executor(aid: str) -> None:
        await sb.run(ScenarioBuilderInput(analysis_id=aid))

    async def ibs_executor(aid: str) -> None:
        await ibs.run(InvestorBriefSynthesizerInput(analysis_id=aid))

    async def set_complexity_tier(aid: str, tier: str) -> str:
        if aid == analysis_id:
            store["complexity_tier"] = tier
        return ""

    async def set_active_sources(aid: str, active_sources: list[str]) -> str:
        if aid == analysis_id:
            lead_plan = store.get("lead_plan") or {}
            lead_plan["active_sources"] = list(active_sources)
            store["lead_plan"] = lead_plan
        return ""

    patches = [
        ("backend.database.queries.get_analysis_by_id", get_analysis),
        ("backend.database.queries.save_harvester_output", save_harvester),
        ("backend.database.queries.save_parser_output", save_parser),
        ("backend.database.queries.save_scenario_output", save_scenario),
        ("backend.database.queries.save_investor_brief", save_investor_brief),
        
        ("backend.database.queries.update_analysis_status", update_status),
        
        ("backend.database.queries.set_analysis_complexity_tier", set_complexity_tier),
        ("backend.database.queries.set_analysis_active_sources", set_active_sources),
        ("backend.services.resume_service.get_analysis_by_id", get_analysis),
        ("backend.services.retry_service.get_analysis_by_id", get_analysis),
        ("backend.services.pipeline_runner.get_analysis_by_id", get_analysis),
        ("backend.agents.prospectus_parser.get_analysis_by_id", get_analysis),
        ("backend.agents.scenario_builder.get_analysis_by_id", get_analysis),
        ("backend.agents.investor_brief_synthesizer.get_analysis_by_id", get_analysis),
        
        ("backend.agents.data_harvester.save_harvester_output", save_harvester),
        ("backend.agents.prospectus_parser.save_parser_output", save_parser),
        ("backend.agents.scenario_builder.save_scenario_output", save_scenario),
        ("backend.agents.investor_brief_synthesizer.save_investor_brief", save_investor_brief),
        
        
        ("backend.services.analysis_status_service.update_analysis_status", update_status),
    ]
    log_return = {"id": str(uuid4())}
    with ExitStack() as stack:
        stack.enter_context(patch("backend.api.websocket_progress.emit_agent_status"))
        stack.enter_context(patch("backend.services.pipeline_runner.fetch_sec_edgar", new=_mock_sec_edgar))
        stack.enter_context(patch("backend.services.pipeline_runner.fetch_rss_feeds", new=_mock_rss))
        stack.enter_context(patch("backend.services.pipeline_runner.fetch_news_api", new=_mock_news_api))
        stack.enter_context(patch("backend.services.pipeline_runner.fetch_crunchbase", new=_mock_crunchbase))
        stack.enter_context(patch("backend.services.pipeline_runner.fetch_yahoo_finance", new=_mock_yahoo))
        stack.enter_context(patch("backend.services.pipeline_runner.fetch_fred_data", new=_mock_fred))
        stack.enter_context(patch("backend.services.pipeline_runner.fetch_twitter", new=_mock_twitter))
        stack.enter_context(patch("backend.services.pipeline_runner.InvestorBriefSynthesizer", new=MockInvestorBriefSynthesizer))
        for target, side_effect in patches:
            stack.enter_context(
                patch(target, new_callable=AsyncMock, side_effect=side_effect)
            )
        for mod in ["data_harvester", "prospectus_parser", "scenario_builder", "investor_brief_synthesizer"]:
            stack.enter_context(
                patch(f"backend.agents.{mod}.log_agent_run_start", new_callable=AsyncMock, return_value=log_return)
            )
            stack.enter_context(
                patch(f"backend.agents.{mod}.log_agent_run_completed", new_callable=AsyncMock)
            )

        executors = pipeline_runner._build_executors()
        result = await resume_from_last_completed_agent(
            ResumeServiceInput(analysis_id=analysis_id),
            executors=executors,
        )

    assert result.completed is True
    assert result.analysis_id == analysis_id
    expected_classifier = classify_complexity(
        ComplexityClassifierInput(
            company_name=store["company_name"],
            has_s1_filed=False,
            media_coverage_score=0,
            source_count_hint=5,
        )
    )
    assert store["complexity_tier"] == expected_classifier.complexity_tier
    scenario_output = store.get("scenario_output")
    assert scenario_output is not None
    scenarios = scenario_output.get("scenarios")
    assert isinstance(scenarios, dict)
    assert "pessimistic" in scenarios
    assert "realistic" in scenarios
    assert "optimistic" in scenarios

    investor_brief = store.get("investor_brief")
    assert isinstance(investor_brief, dict)
    assert "company_name" in investor_brief
    assert "sector_theme" in investor_brief
    assert "primary_instrument" in investor_brief
    assert "overview_markdown" in investor_brief
    assert "references" in investor_brief
