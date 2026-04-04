from typing import Awaitable, Callable
from typing import Any, TypedDict

from pydantic import BaseModel, Field

from backend.database.queries import get_analysis_by_id
from backend.services.analysis_status_service import (
    mark_agent_completed,
    set_analysis_completed,
    set_analysis_failed,
    set_analysis_running,
)
from backend.services.retry_service import retry_agent_once_on_null_output

AgentExecutor = Callable[[str], Awaitable[object]]

_PIPELINE_ORDER: tuple[str, ...] = (
    "single_agent",
)


class ResumeServiceInput(BaseModel):
    analysis_id: str


class ResumeServiceResult(BaseModel):
    analysis_id: str
    resumed_from: str | None = None
    executed_agents: list[str] = Field(default_factory=list)
    completed: bool


class _ResumeState(TypedDict):
    analysis_id: str
    executed_agents: list[str]


async def resume_from_last_completed_agent(
    payload: ResumeServiceInput,
    executors: dict[str, AgentExecutor],
) -> ResumeServiceResult:
    analysis = await get_analysis_by_id(payload.analysis_id)
    if analysis is None:
        raise RuntimeError(f"Analysis not found for analysis_id={payload.analysis_id}")

    last_completed = _normalize_agent_name(analysis.get("last_completed_agent"))
    start_index = _next_agent_index(last_completed)
    agents_to_run = list(_PIPELINE_ORDER[start_index:])

    for agent_name in agents_to_run:
        if agent_name not in executors:
            raise RuntimeError(f"Missing executor for {agent_name}")

    await set_analysis_running(
        analysis_id=payload.analysis_id,
        last_completed_agent=last_completed,
    )

    executed_tracker: list[str] = []
    executed_agents: list[str] = []
    current_agent: str | None = None
    try:
        for agent_name in agents_to_run:
            current_agent = agent_name
            await retry_agent_once_on_null_output(
                analysis_id=payload.analysis_id,
                agent_name=agent_name,
                executor=executors[agent_name],
            )
            await mark_agent_completed(
                analysis_id=payload.analysis_id,
                agent_name=agent_name,
            )
            executed_agents.append(agent_name)
            executed_tracker.append(agent_name)
    except Exception:
        row = await get_analysis_by_id(payload.analysis_id)
        if row is not None and str(row.get("status") or "") == "failed":
            raise
        failed_at = executed_tracker[-1] if executed_tracker else (current_agent or last_completed)
        await set_analysis_failed(
            analysis_id=payload.analysis_id,
            last_completed_agent=failed_at,
        )
        raise

    final_last_completed = executed_agents[-1] if executed_agents else last_completed
    await set_analysis_completed(
        analysis_id=payload.analysis_id,
        last_completed_agent=final_last_completed,
    )
    return ResumeServiceResult(
        analysis_id=payload.analysis_id,
        resumed_from=last_completed,
        executed_agents=executed_agents,
        completed=True,
    )


def _normalize_agent_name(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    return text


def _next_agent_index(last_completed_agent: str | None) -> int:
    if last_completed_agent is None:
        return 0
    try:
        return _PIPELINE_ORDER.index(last_completed_agent) + 1
    except ValueError:
        raise RuntimeError(f"Unknown last_completed_agent value: {last_completed_agent}") from None


