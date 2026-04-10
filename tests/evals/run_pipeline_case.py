from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from backend.models.eval_case import EvalCase
from backend.models.harvester_output import (
    CrunchbaseData,
    FredData,
    NewsArticle,
    SecFiling,
    TwitterData,
    TwitterSentimentScore,
    YahooFinanceData,
)
from backend.services import pipeline_runner
from backend.services.resume_service import ResumeServiceInput, resume_from_last_completed_agent


@dataclass
class PipelineCaseRunResult:
    case_id: str
    final_report: dict[str, Any] | None
    parser_output: dict[str, Any] | None
    scenario_output: dict[str, Any] | None
    harvester_output: dict[str, Any] | None


def _filing_type_for_case(case: EvalCase) -> str:
    ft = case.filing_type
    if ft == "424B4":
        return "424B4"
    if ft == "S-1":
        return "S-1"
    if ft == "S-1_and_424B4":
        return "S-1"
    return "S-1"


def _synthetic_10k_text(case: EvalCase) -> str:
    return (
        "Form 10-K Annual Report\n"
        "MANAGEMENT'S DISCUSSION AND ANALYSIS\n"
        "Consolidated Statements of Operations. Total revenue was $1.0 million "
        "for the year ended December 31, 2024.\n"
        "Cash used in operating activities was $2.0 million for the year ended December 31, 2024.\n"
        f"Case marker: {case.case_id}\n"
    )


async def _mock_crunchbase(company_name: str) -> CrunchbaseData:
    return CrunchbaseData(investors=["EvalTest"])


async def _mock_yahoo(company_name: str) -> YahooFinanceData:
    return YahooFinanceData(sector_90d_performance=0.0)


async def _mock_fred() -> FredData:
    return FredData()


async def _mock_twitter(company_name: str) -> TwitterData:
    return TwitterData(sentiment_score=TwitterSentimentScore(positive=0.2, negative=0.2, neutral=0.6))


def _base_ipo_price_history() -> dict[str, Any]:
    return {
        "ipo_price": 10.0,
        "current_price": 10.5,
        "peak_price": 12.0,
        "trough_price": 9.5,
        "performance_since_ipo_pct": 5.0,
        "lock_up_cliff_date": "2024-09-01",
        "price_at_lock_up_cliff": 9.8,
    }


async def run_pipeline_case(case: EvalCase, inject_post_ipo_10k: bool = False) -> PipelineCaseRunResult:
    analysis_id = str(uuid4())
    store: dict[str, Any] = {
        "id": analysis_id,
        "company_name": case.company_name,
        "complexity_tier": "standard",
        "status": "pending",
        "last_completed_agent": None,
        "harvester_output": None,
        "parser_output": None,
        "scenario_output": None,
        "final_report": None,
        "created_at": datetime.now(timezone.utc),
    }

    async def get_analysis(aid: str) -> dict[str, Any] | None:
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

    async def save_final_report(*args: object, **kw: object) -> str:
        aid = kw.get("analysis_id")
        out = kw.get("output")
        if aid is None and args:
            aid = args[0]
        if out is None and len(args) > 1:
            out = args[1]
        if aid == analysis_id:
            store["final_report"] = out
        return ""

    async def update_status(*args: object, **kwargs: object) -> str:
        aid = kwargs.get("analysis_id", args[0] if args else "")
        if aid == analysis_id:
            store["status"] = str(kwargs.get("status", args[1] if len(args) > 1 else ""))
            lca = kwargs.get("last_completed_agent")
            if lca is not None:
                store["last_completed_agent"] = lca
        return ""

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

    async def set_analysis_ticker_and_ipo_date(
        aid: str,
        ticker: str | None,
        ipo_date: Any | None,
    ) -> str:
        if aid == analysis_id:
            store["ticker"] = ticker
            store["ipo_date"] = ipo_date
        return ""

    async def mock_sec_edgar(company_name: str) -> list[SecFiling]:
        return [
            SecFiling(
                url=case.filing_url or "https://www.sec.gov/edgar/mock",
                text=case.filing_excerpt,
                filing_type=_filing_type_for_case(case),
            )
        ]

    async def mock_news_api(company_name: str) -> list[NewsArticle]:
        return [
            NewsArticle(
                source=case.article_source,
                title=case.article_title,
                date=datetime.now(timezone.utc),
                content=case.pre_ipo_news_excerpt,
                url=case.article_url,
                is_primary_source=True,
            )
        ]

    async def mock_rss(company_name: str) -> list[NewsArticle]:
        return []

    ten_k_payload = _synthetic_10k_text(case) if inject_post_ipo_10k else None

    patches: list[tuple[str, Any]] = [
        ("backend.database.queries.get_analysis_by_id", get_analysis),
        ("backend.database.queries.save_harvester_output", save_harvester),
        ("backend.database.queries.save_parser_output", save_parser),
        ("backend.database.queries.save_scenario_output", save_scenario),
        ("backend.database.queries.save_final_report", save_final_report),
        ("backend.database.queries.update_analysis_status", update_status),
        ("backend.database.queries.set_analysis_complexity_tier", set_complexity_tier),
        ("backend.database.queries.set_analysis_active_sources", set_active_sources),
        ("backend.agents.single_agent_tool_caller.get_analysis_by_id", get_analysis),
        ("backend.agents.single_agent_tool_caller.set_analysis_complexity_tier", set_complexity_tier),
        ("backend.agents.single_agent_tool_caller.set_analysis_active_sources", set_active_sources),
        ("backend.services.resume_service.get_analysis_by_id", get_analysis),
        ("backend.services.retry_service.get_analysis_by_id", get_analysis),
        ("backend.agents.prospectus_parser.get_analysis_by_id", get_analysis),
        ("backend.agents.scenario_builder.get_analysis_by_id", get_analysis),
        ("backend.agents.data_harvester.save_harvester_output", save_harvester),
        ("backend.agents.prospectus_parser.save_parser_output", save_parser),
        ("backend.agents.scenario_builder.save_scenario_output", save_scenario),
        ("backend.agents.single_agent_tool_caller.save_final_report", save_final_report),
        ("backend.agents.single_agent_tool_caller.set_analysis_ticker_and_ipo_date", set_analysis_ticker_and_ipo_date),
        ("backend.services.analysis_status_service.update_analysis_status", update_status),
    ]
    log_return = {"id": str(uuid4())}
    with ExitStack() as stack:
        stack.enter_context(patch("backend.api.websocket_progress.emit_agent_status"))
        stack.enter_context(patch("backend.agents.single_agent_tool_caller.fetch_sec_edgar", new=mock_sec_edgar))
        stack.enter_context(patch("backend.agents.single_agent_tool_caller.fetch_rss_feeds", new=mock_rss))
        stack.enter_context(patch("backend.agents.single_agent_tool_caller.fetch_news_api", new=mock_news_api))
        stack.enter_context(patch("backend.agents.single_agent_tool_caller.fetch_crunchbase", new=_mock_crunchbase))
        stack.enter_context(patch("backend.agents.single_agent_tool_caller.fetch_yahoo_finance", new=_mock_yahoo))
        stack.enter_context(patch("backend.agents.single_agent_tool_caller.fetch_fred_data", new=_mock_fred))
        stack.enter_context(patch("backend.agents.single_agent_tool_caller.fetch_twitter", new=_mock_twitter))
        stack.enter_context(
            patch(
                "backend.agents.single_agent_tool_caller.resolve_ticker_from_input",
                new_callable=AsyncMock,
                return_value="MOCK",
            )
        )
        stack.enter_context(
            patch(
                "backend.agents.single_agent_tool_caller.resolve_ipo_date_for_ticker",
                new_callable=AsyncMock,
                return_value=date(2023, 9, 14),
            )
        )
        stack.enter_context(
            patch(
                "backend.agents.single_agent_tool_caller.fetch_ipo_price_history",
                new_callable=AsyncMock,
                return_value=_base_ipo_price_history(),
            )
        )
        stack.enter_context(
            patch(
                "backend.agents.data_harvester.fetch_post_ipo_filings",
                new_callable=AsyncMock,
                return_value=ten_k_payload,
            )
        )
        stack.enter_context(
            patch(
                "backend.agents.single_agent_tool_caller.NarrativeSynthesiser.synthesise",
                new_callable=AsyncMock,
                return_value=None,
            )
        )
        for target, side_effect in patches:
            stack.enter_context(patch(target, new_callable=AsyncMock, side_effect=side_effect))
        for mod in [
            "single_agent_tool_caller",
            "data_harvester",
            "prospectus_parser",
            "scenario_builder",
        ]:
            stack.enter_context(
                patch(f"backend.agents.{mod}.log_agent_run_start", new_callable=AsyncMock, return_value=log_return)
            )
            stack.enter_context(patch(f"backend.agents.{mod}.log_agent_run_completed", new_callable=AsyncMock))
            stack.enter_context(patch(f"backend.agents.{mod}.log_agent_run_failed", new_callable=AsyncMock))

        executors = pipeline_runner._build_executors()
        result = await resume_from_last_completed_agent(
            ResumeServiceInput(analysis_id=analysis_id),
            executors=executors,
        )

    assert result.completed is True
    return PipelineCaseRunResult(
        case_id=case.case_id,
        final_report=store.get("final_report"),
        parser_output=store.get("parser_output"),
        scenario_output=store.get("scenario_output"),
        harvester_output=store.get("harvester_output"),
    )
