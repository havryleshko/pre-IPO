import importlib
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
    "data_harvester",
    "prospectus_parser",
    "scenario_builder",
    "investor_brief_synthesizer",
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
    graph = _build_resume_graph(
        agents_to_run=agents_to_run,
        executors=executors,
        executed_tracker=executed_tracker,
    )
    try:
        final_state = await graph.ainvoke(
            {
                "analysis_id": payload.analysis_id,
                "executed_agents": [],
            }
        )
        executed = final_state.get("executed_agents", [])
    except Exception:
        await set_analysis_failed(
            analysis_id=payload.analysis_id,
            last_completed_agent=executed_tracker[-1] if executed_tracker else last_completed,
        )
        raise

    final_last_completed = executed[-1] if executed else last_completed
    await set_analysis_completed(
        analysis_id=payload.analysis_id,
        last_completed_agent=final_last_completed,
    )
    return ResumeServiceResult(
        analysis_id=payload.analysis_id,
        resumed_from=last_completed,
        executed_agents=executed,
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


def _build_resume_graph(
    agents_to_run: list[str],
    executors: dict[str, AgentExecutor],
    executed_tracker: list[str],
) -> Any:
    state_graph_cls, start_node, end_node = _load_langgraph_graph_components()
    graph_builder = state_graph_cls(_ResumeState)
    previous_node: str = start_node

    for agent_name in agents_to_run:
        node_name = f"run_{agent_name}"

        async def _run_agent(state: _ResumeState, current_agent: str = agent_name) -> _ResumeState:
            await retry_agent_once_on_null_output(
                analysis_id=state["analysis_id"],
                agent_name=current_agent,
                executor=executors[current_agent],
            )
            await mark_agent_completed(
                analysis_id=state["analysis_id"],
                agent_name=current_agent,
            )
            executed_agents = [*state["executed_agents"], current_agent]
            executed_tracker.clear()
            executed_tracker.extend(executed_agents)
            return {
                "analysis_id": state["analysis_id"],
                "executed_agents": executed_agents,
            }

        graph_builder.add_node(node_name, _run_agent)
        graph_builder.add_edge(previous_node, node_name)
        previous_node = node_name

    graph_builder.add_edge(previous_node, end_node)
    return graph_builder.compile()


def _load_langgraph_graph_components() -> tuple[Any, str, str]:
    module = importlib.import_module("langgraph.graph")
    state_graph_cls = getattr(module, "StateGraph")
    start_node = getattr(module, "START")
    end_node = getattr(module, "END")
    return state_graph_cls, start_node, end_node
