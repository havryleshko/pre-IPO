import logging

from backend.agents.complexity_classifier import ComplexityClassifierInput, classify_complexity
from backend.agents.data_harvester import DataHarvester, DataHarvesterInput
from backend.agents.investor_brief_synthesizer import InvestorBriefSynthesizer, InvestorBriefSynthesizerInput
from backend.agents.prospectus_parser import ProspectusParser, ProspectusParserInput
from backend.agents.scenario_builder import ScenarioBuilder, ScenarioBuilderInput
from backend.api.websocket_progress import emit_agent_status
from backend.database.queries import (
    get_analysis_by_id,
    set_analysis_active_sources,
    set_analysis_complexity_tier,
)
from backend.services.resume_service import ResumeServiceInput, resume_from_last_completed_agent
from backend.tools.crunchbase_client import fetch_crunchbase
from backend.tools.fred_client import fetch_fred_data
from backend.tools.newsapi_client import fetch_news_api
from backend.tools.rss_client import fetch_rss_feeds
from backend.tools.sec_edgar_client import fetch_sec_edgar
from backend.tools.twitter_client import fetch_twitter
from backend.tools.yfinance_client import fetch_yahoo_finance

logger = logging.getLogger(__name__)

def _derive_pre_harvest_complexity_hints(analysis: dict) -> dict[str, object]:
    requested_tier = str(analysis.get("complexity_tier") or "").strip().lower()

    harvester_output = analysis.get("harvester_output") or {}
    parser_output = analysis.get("parser_output") or {}

    sec_filings = harvester_output.get("sec_filings") or []
    has_s1_filed = bool(parser_output) or any(
        "s-1" in str(filing.get("filing_type") or "").lower() for filing in sec_filings if isinstance(filing, dict)
    )

    news_articles = harvester_output.get("news_articles") or []
    article_count = len(news_articles) if isinstance(news_articles, list) else 0
    media_coverage_score = max(0, min(100, article_count * 5))

    source_count_hint = 0
    if requested_tier == "complex":
        source_count_hint = 7
    elif requested_tier == "standard":
        source_count_hint = 5
    elif requested_tier == "simple":
        source_count_hint = 3

    return {
        "has_s1_filed": has_s1_filed,
        "media_coverage_score": int(media_coverage_score),
        "source_count_hint": int(source_count_hint),
    }


def _emit_status(analysis_id: str, agent_name: str, status: str) -> None:
    emit_agent_status(analysis_id=analysis_id, agent_name=agent_name, status=status)


def _wrap_executor(agent_name: str, fn):
    async def _wrapped(analysis_id: str) -> None:
        _emit_status(analysis_id, agent_name, "running")
        try:
            await fn(analysis_id)
        except Exception:
            _emit_status(analysis_id, agent_name, "failed")
            raise
        _emit_status(analysis_id, agent_name, "completed")

    return _wrapped


async def run_analysis_pipeline(analysis_id: str) -> None:
    _emit_status(analysis_id, "lead_orchestrator", "running")
    try:
        executors = _build_executors()
        await resume_from_last_completed_agent(
            ResumeServiceInput(analysis_id=analysis_id),
            executors=executors,
        )
    except Exception:
        _emit_status(analysis_id, "lead_orchestrator", "failed")
        logger.exception("Pipeline failed for analysis_id=%s", analysis_id)
        raise
    _emit_status(analysis_id, "lead_orchestrator", "completed")


def _build_executors():
    data_harvester = DataHarvester(
        sec_edgar=fetch_sec_edgar,
        rss_feeds=fetch_rss_feeds,
        news_api=fetch_news_api,
        crunchbase=fetch_crunchbase,
        yahoo_finance=fetch_yahoo_finance,
        fred=fetch_fred_data,
        twitter=fetch_twitter,
    )
    prospectus_parser = ProspectusParser()
    scenario_builder = ScenarioBuilder()
    investor_brief_synthesizer = InvestorBriefSynthesizer()

    async def _data_harvester_executor(analysis_id: str) -> None:
        analysis = await get_analysis_by_id(analysis_id)
        if analysis is None:
            raise RuntimeError(f"Analysis not found for analysis_id={analysis_id}")
        company_name = str(analysis.get("company_name") or "").strip()
        if not company_name:
            raise RuntimeError(f"Missing company name for analysis_id={analysis_id}")
        hints = _derive_pre_harvest_complexity_hints(analysis)
        classifier = classify_complexity(
            ComplexityClassifierInput(
                company_name=company_name,
                has_s1_filed=bool(hints["has_s1_filed"]),
                media_coverage_score=int(hints["media_coverage_score"]),
                source_count_hint=int(hints["source_count_hint"]),
            )
        )
        await set_analysis_complexity_tier(analysis_id, classifier.complexity_tier)
        await set_analysis_active_sources(analysis_id, classifier.active_sources)
        await data_harvester.run(
            DataHarvesterInput(
                analysis_id=analysis_id,
                company_name=company_name,
                complexity_tier=classifier.complexity_tier,
                active_sources=classifier.active_sources,
            )
        )

    async def _prospectus_parser_executor(analysis_id: str) -> None:
        await prospectus_parser.run(ProspectusParserInput(analysis_id=analysis_id))

    async def _scenario_builder_executor(analysis_id: str) -> None:
        await scenario_builder.run(ScenarioBuilderInput(analysis_id=analysis_id))

    async def _investor_brief_synthesizer_executor(analysis_id: str) -> None:
        await investor_brief_synthesizer.run(InvestorBriefSynthesizerInput(analysis_id=analysis_id))

    return {
        "data_harvester": _wrap_executor("data_harvester", _data_harvester_executor),
        "prospectus_parser": _wrap_executor("prospectus_parser", _prospectus_parser_executor),
        "scenario_builder": _wrap_executor("scenario_builder", _scenario_builder_executor),
        "investor_brief_synthesizer": _wrap_executor("investor_brief_synthesizer", _investor_brief_synthesizer_executor),
    }
