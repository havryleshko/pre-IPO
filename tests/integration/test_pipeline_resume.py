from unittest.mock import AsyncMock, patch

import pytest

from backend.services.resume_service import (
    ResumeServiceInput,
    resume_from_last_completed_agent,
)


def _analysis(last_completed_agent: str | None = None) -> dict:
    return {
        "id": "test-analysis-id",
        "company_name": "TestCo",
        "last_completed_agent": last_completed_agent,
        "final_report": {},
    }


def _make_executor(executed: list[str]):
    async def _executor(analysis_id: str) -> None:
        executed.append("single_agent")

    return _executor


@pytest.mark.asyncio
async def test_resume_from_none_runs_single_agent() -> None:
    executed: list[str] = []
    executors = {"single_agent": _make_executor(executed)}
    analysis = _analysis(last_completed_agent=None)

    async def get_analysis(aid: str):
        return analysis

    set_running = AsyncMock()
    mark_completed = AsyncMock()
    set_completed = AsyncMock()
    with (
        patch("backend.services.resume_service.get_analysis_by_id", new_callable=AsyncMock, side_effect=get_analysis),
        patch("backend.services.retry_service.get_analysis_by_id", new_callable=AsyncMock, side_effect=get_analysis),
        patch("backend.services.resume_service.set_analysis_running", set_running),
        patch("backend.services.resume_service.mark_agent_completed", mark_completed),
        patch("backend.services.resume_service.set_analysis_completed", set_completed),
    ):
        result = await resume_from_last_completed_agent(
            ResumeServiceInput(analysis_id="test-id"),
            executors=executors,
        )

    assert result.analysis_id == "test-id"
    assert result.resumed_from is None
    assert result.executed_agents == ["single_agent"]
    assert executed == ["single_agent"]


@pytest.mark.asyncio
async def test_resume_from_single_agent_skips_execution() -> None:
    executed: list[str] = []
    executors = {"single_agent": _make_executor(executed)}
    analysis = _analysis(last_completed_agent="single_agent")

    set_running = AsyncMock()
    mark_completed = AsyncMock()
    set_completed = AsyncMock()
    with (
        patch("backend.services.resume_service.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis),
        patch("backend.services.retry_service.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis),
        patch("backend.services.resume_service.set_analysis_running", set_running),
        patch("backend.services.resume_service.mark_agent_completed", mark_completed),
        patch("backend.services.resume_service.set_analysis_completed", set_completed),
    ):
        result = await resume_from_last_completed_agent(
            ResumeServiceInput(analysis_id="test-id"),
            executors=executors,
        )

    assert result.resumed_from == "single_agent"
    assert result.executed_agents == []
    assert executed == []
    mark_completed.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_failure_sets_last_completed_to_last_successful() -> None:
    async def failing_executor(analysis_id: str) -> None:
        raise RuntimeError("agent failed")

    executors = {"single_agent": failing_executor}
    analysis = _analysis(last_completed_agent=None)

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

    set_failed_mock.assert_awaited_once_with(analysis_id="test-id", last_completed_agent=None)
