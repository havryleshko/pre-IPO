from unittest.mock import AsyncMock, patch

import pytest

from backend.services.resume_service import (
    ResumeServiceInput,
    resume_from_last_completed_agent,
)


def _analysis_with_outputs(last_completed_agent: str | None = None) -> dict:
    return {
        "id": "test-analysis-id",
        "company_name": "TestCo",
        "last_completed_agent": last_completed_agent,
        "harvester_output": {},
        "parser_output": {},
        "scenario_output": {},
        "recommendation_output": {},
        "judge_output": {},
    }


def _make_executor(executed: list[str], name: str):
    async def executor(analysis_id: str) -> None:
        executed.append(name)

    return executor


@pytest.mark.asyncio
async def test_resume_from_none_runs_all_agents() -> None:
    executed: list[str] = []
    executors = {
        "data_harvester": _make_executor(executed, "data_harvester"),
        "prospectus_parser": _make_executor(executed, "prospectus_parser"),
        "scenario_builder": _make_executor(executed, "scenario_builder"),
        "recommendation_engine": _make_executor(executed, "recommendation_engine"),
        "judge_agent": _make_executor(executed, "judge_agent"),
    }
    analysis = _analysis_with_outputs(last_completed_agent=None)
    with (
        patch("backend.services.resume_service.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis),
        patch("backend.services.retry_service.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis),
        patch("backend.services.resume_service.set_analysis_running", new_callable=AsyncMock),
        patch("backend.services.resume_service.mark_agent_completed", new_callable=AsyncMock),
        patch("backend.services.resume_service.set_analysis_completed", new_callable=AsyncMock),
    ):
        result = await resume_from_last_completed_agent(
            ResumeServiceInput(analysis_id="test-id"),
            executors=executors,
        )
    assert result.analysis_id == "test-id"
    assert result.resumed_from is None
    assert result.executed_agents == [
        "data_harvester",
        "prospectus_parser",
        "scenario_builder",
        "recommendation_engine",
        "judge_agent",
    ]
    assert result.completed is True


@pytest.mark.asyncio
async def test_resume_from_prospectus_parser_skips_data_harvester_and_parser() -> None:
    executed: list[str] = []
    executors = {
        "data_harvester": _make_executor(executed, "data_harvester"),
        "prospectus_parser": _make_executor(executed, "prospectus_parser"),
        "scenario_builder": _make_executor(executed, "scenario_builder"),
        "recommendation_engine": _make_executor(executed, "recommendation_engine"),
        "judge_agent": _make_executor(executed, "judge_agent"),
    }
    analysis = _analysis_with_outputs(last_completed_agent="prospectus_parser")
    with (
        patch("backend.services.resume_service.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis),
        patch("backend.services.retry_service.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis),
        patch("backend.services.resume_service.set_analysis_running", new_callable=AsyncMock),
        patch("backend.services.resume_service.mark_agent_completed", new_callable=AsyncMock),
        patch("backend.services.resume_service.set_analysis_completed", new_callable=AsyncMock),
    ):
        result = await resume_from_last_completed_agent(
            ResumeServiceInput(analysis_id="test-id"),
            executors=executors,
        )
    assert result.resumed_from == "prospectus_parser"
    assert result.executed_agents == [
        "scenario_builder",
        "recommendation_engine",
        "judge_agent",
    ]
    assert "data_harvester" not in result.executed_agents
    assert "prospectus_parser" not in result.executed_agents


@pytest.mark.asyncio
async def test_resume_from_scenario_builder_runs_only_recommendation_and_judge() -> None:
    executed: list[str] = []
    executors = {
        "data_harvester": _make_executor(executed, "data_harvester"),
        "prospectus_parser": _make_executor(executed, "prospectus_parser"),
        "scenario_builder": _make_executor(executed, "scenario_builder"),
        "recommendation_engine": _make_executor(executed, "recommendation_engine"),
        "judge_agent": _make_executor(executed, "judge_agent"),
    }
    analysis = _analysis_with_outputs(last_completed_agent="scenario_builder")
    with (
        patch("backend.services.resume_service.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis),
        patch("backend.services.retry_service.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis),
        patch("backend.services.resume_service.set_analysis_running", new_callable=AsyncMock),
        patch("backend.services.resume_service.mark_agent_completed", new_callable=AsyncMock),
        patch("backend.services.resume_service.set_analysis_completed", new_callable=AsyncMock),
    ):
        result = await resume_from_last_completed_agent(
            ResumeServiceInput(analysis_id="test-id"),
            executors=executors,
        )
    assert result.resumed_from == "scenario_builder"
    assert result.executed_agents == ["recommendation_engine", "judge_agent"]


@pytest.mark.asyncio
async def test_resume_failure_sets_last_completed_to_last_successful() -> None:
    async def failing_executor(analysis_id: str) -> None:
        raise RuntimeError("agent failed")

    async def noop_executor(analysis_id: str) -> None:
        pass

    executors = {
        "data_harvester": noop_executor,
        "prospectus_parser": noop_executor,
        "scenario_builder": failing_executor,
        "recommendation_engine": noop_executor,
        "judge_agent": noop_executor,
    }
    analysis = _analysis_with_outputs(last_completed_agent="prospectus_parser")
    set_failed_mock = AsyncMock()
    with (
        patch("backend.services.resume_service.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis),
        patch("backend.services.retry_service.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis),
        patch("backend.services.resume_service.set_analysis_running", new_callable=AsyncMock),
        patch("backend.services.resume_service.set_analysis_failed", set_failed_mock),
    ):
        with pytest.raises(RuntimeError, match="agent failed"):
            await resume_from_last_completed_agent(
                ResumeServiceInput(analysis_id="test-id"),
                executors=executors,
            )
    set_failed_mock.assert_called_once()
    assert set_failed_mock.call_args.kwargs["last_completed_agent"] == "prospectus_parser"
