import logging
from datetime import date, datetime
from typing import Any

from backend.agents.single_agent_tool_caller import (
    SingleAgentToolCaller,
    SingleAgentToolCallerInput,
)
from backend.api.websocket_progress import emit_agent_status
from backend.services.resume_service import ResumeServiceInput, resume_from_last_completed_agent

logger = logging.getLogger(__name__)


def _coerce_row_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None

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
    try:
        executors = _build_executors()
        await resume_from_last_completed_agent(
            ResumeServiceInput(analysis_id=analysis_id),
            executors=executors,
        )
    except Exception:
        logger.exception("Pipeline failed for analysis_id=%s", analysis_id)
        raise


def _build_executors():
    single_agent = SingleAgentToolCaller()

    async def _single_agent_executor(analysis_id: str) -> None:
        await single_agent.run(SingleAgentToolCallerInput(analysis_id=analysis_id))

    return {"single_agent": _wrap_executor("single_agent", _single_agent_executor)}
