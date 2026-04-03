from unittest.mock import AsyncMock, patch

import pytest

from backend.services.retry_service import retry_agent_once_on_null_output


@pytest.mark.asyncio
async def test_retry_succeeds_when_second_run_produces_output() -> None:
    get_count = 0

    async def get_analysis(analysis_id: str):
        nonlocal get_count
        get_count += 1
        if get_count <= 1:
            return {"id": analysis_id, "harvester_output": None}
        return {"id": analysis_id, "harvester_output": {}}

    executor_calls: list[str] = []

    async def executor(analysis_id: str) -> None:
        executor_calls.append(analysis_id)

    with (
        patch("backend.services.retry_service.get_analysis_by_id", new_callable=AsyncMock, side_effect=get_analysis),
    ):
        result = await retry_agent_once_on_null_output(
            analysis_id="test-id",
            agent_name="data_harvester",
            executor=executor,
        )
    assert result is True
    assert len(executor_calls) == 2


@pytest.mark.asyncio
async def test_retry_fails_fail_fast_raises_and_sets_status() -> None:
    analysis_null = {"id": "test-id", "harvester_output": None}

    async def executor(analysis_id: str) -> None:
        pass

    set_failed_mock = AsyncMock()
    with (
        patch("backend.services.retry_service.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis_null),
        patch("backend.services.retry_service.set_analysis_failed", set_failed_mock),
    ):
        with pytest.raises(RuntimeError, match="null output persisted after single retry"):
            await retry_agent_once_on_null_output(
                analysis_id="test-id",
                agent_name="data_harvester",
                executor=executor,
            )
    set_failed_mock.assert_called_once_with(
        analysis_id="test-id",
        last_completed_agent="data_harvester",
    )


@pytest.mark.asyncio
async def test_first_run_succeeds_no_retry() -> None:
    analysis_ok = {"id": "test-id", "harvester_output": {}}
    executor_calls: list[str] = []

    async def executor(analysis_id: str) -> None:
        executor_calls.append(analysis_id)

    with (
        patch("backend.services.retry_service.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis_ok),
    ):
        result = await retry_agent_once_on_null_output(
            analysis_id="test-id",
            agent_name="data_harvester",
            executor=executor,
        )
    assert result is True
    assert len(executor_calls) == 1


@pytest.mark.asyncio
async def test_single_agent_retry_succeeds_when_output_valid() -> None:
    get_count = 0

    async def get_analysis(analysis_id: str) -> dict:
        nonlocal get_count
        get_count += 1
        if get_count <= 1:
            return {"id": analysis_id, "final_report": None}
        return {"id": analysis_id, "final_report": {"company_name": "Co"}}

    async def executor(analysis_id: str) -> None:
        pass

    with patch("backend.services.retry_service.get_analysis_by_id", new_callable=AsyncMock, side_effect=get_analysis):
        result = await retry_agent_once_on_null_output(
            analysis_id="test-id",
            agent_name="single_agent",
            executor=executor,
        )
    assert result is True
    assert get_count == 2


@pytest.mark.asyncio
async def test_single_agent_invalid_dict_triggers_retry_then_failure() -> None:
    async def get_analysis(analysis_id: str) -> dict:
        return {"id": analysis_id, "final_report": {}}

    async def executor(analysis_id: str) -> None:
        pass

    set_failed_mock = AsyncMock()
    with (
        patch("backend.services.retry_service.get_analysis_by_id", new_callable=AsyncMock, side_effect=get_analysis),
        patch("backend.services.retry_service.set_analysis_failed", set_failed_mock),
    ):
        with pytest.raises(RuntimeError, match="null output persisted"):
            await retry_agent_once_on_null_output(
                analysis_id="test-id",
                agent_name="single_agent",
                executor=executor,
            )
    set_failed_mock.assert_called_once_with(
        analysis_id="test-id",
        last_completed_agent="single_agent",
    )
