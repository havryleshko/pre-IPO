from typing import Awaitable, Callable

from backend.database.queries import get_analysis_by_id
from backend.services.analysis_status_service import set_analysis_failed

AgentExecutor = Callable[[str], Awaitable[object]]

_AGENT_OUTPUT_FIELD: dict[str, str] = {
    "data_harvester": "harvester_output",
    "prospectus_parser": "parser_output",
    "scenario_builder": "scenario_output",
    "investor_brief_synthesizer": "investor_brief",
}


async def retry_agent_once_on_null_output(
    analysis_id: str,
    agent_name: str,
    executor: AgentExecutor,
) -> bool:
    output_field = _output_field_for_agent(agent_name)

    await executor(analysis_id)
    if await _has_non_null_output(analysis_id, output_field):
        return True

    await executor(analysis_id)
    if await _has_non_null_output(analysis_id, output_field):
        return True

    await set_analysis_failed(analysis_id=analysis_id, last_completed_agent=agent_name)
    raise RuntimeError(
        f"Analysis failed at {agent_name}: null output persisted after single retry for analysis_id={analysis_id}"
    )


async def _has_non_null_output(analysis_id: str, output_field: str) -> bool:
    analysis = await get_analysis_by_id(analysis_id)
    if analysis is None:
        return False
    return analysis.get(output_field) is not None


def _output_field_for_agent(agent_name: str) -> str:
    key = agent_name.strip().lower()
    output_field = _AGENT_OUTPUT_FIELD.get(key)
    if output_field is None:
        raise ValueError(f"Unsupported agent for null-output retry: {agent_name}")
    return output_field
