import asyncio
import importlib
import logging
from typing import Any, TypedDict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.schemas import (
    AnalysisOutputsResponse,
    CreateAnalysisRequest,
    CreateAnalysisResponse,
)
from backend.database.queries import (
    create_analysis,
    get_analysis_by_id,
)
from backend.services.pipeline_runner import run_analysis_pipeline

router = APIRouter(prefix="/analyses", tags=["analysis"])
logger = logging.getLogger(__name__)


class _CreateAnalysisState(TypedDict):
    company_name: str
    analysis_record: dict[str, Any] | None


@router.post("", response_model=CreateAnalysisResponse)
async def create_analysis_endpoint(payload: CreateAnalysisRequest) -> CreateAnalysisResponse:
    graph = _build_create_analysis_graph()
    final_state = await graph.ainvoke(
        {
            "company_name": payload.company_name,
            "analysis_record": None,
        }
    )
    record = final_state.get("analysis_record")
    if not record:
        raise HTTPException(status_code=500, detail="Failed to create analysis")
    try:
        _schedule_pipeline(str(record["id"]))
    except Exception:
        logger.exception("Failed to schedule pipeline for analysis_id=%s", record["id"])
    return CreateAnalysisResponse(
        analysis_id=record["id"],
        company_name=record["company_name"],
        status=record["status"],
        complexity_tier=record["complexity_tier"],
        created_at=record["created_at"],
    )


@router.get("/{analysis_id}", response_model=AnalysisOutputsResponse)
async def get_analysis_endpoint(analysis_id: str) -> AnalysisOutputsResponse:
    analysis = await get_analysis_by_id(analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    record = dict(analysis)
    return AnalysisOutputsResponse.model_validate(
        {
            "analysis_id": record["id"],
            "company_name": record["company_name"],
            "status": record["status"],
            "complexity_tier": record["complexity_tier"],
            "last_completed_agent": record.get("last_completed_agent"),
            "created_at": record["created_at"],
            "harvester_output": record.get("harvester_output"),
            "parser_output": record.get("parser_output"),
            "scenario_output": record.get("scenario_output"),
            "investor_brief": record.get("investor_brief"),
        }
    )


def _build_create_analysis_graph() -> Any:
    state_graph_cls, start_node, end_node = _load_langgraph_graph_components()
    graph_builder = state_graph_cls(_CreateAnalysisState)
    graph_builder.add_node("persist_analysis", _persist_analysis_node)
    graph_builder.add_edge(start_node, "persist_analysis")
    graph_builder.add_edge("persist_analysis", end_node)
    return graph_builder.compile()


async def _persist_analysis_node(state: _CreateAnalysisState) -> _CreateAnalysisState:
    created = await create_analysis(company_name=state["company_name"])
    return {
        "company_name": state["company_name"],
        "analysis_record": dict(created) if created is not None else None,
    }


def _load_langgraph_graph_components() -> tuple[Any, str, str]:
    module = importlib.import_module("langgraph.graph")
    state_graph_cls = getattr(module, "StateGraph")
    start_node = getattr(module, "START")
    end_node = getattr(module, "END")
    return state_graph_cls, start_node, end_node


def _schedule_pipeline(analysis_id: str) -> None:
    task = asyncio.create_task(run_analysis_pipeline(analysis_id))

    def _on_done(completed_task: asyncio.Task[None]) -> None:
        exc = completed_task.exception()
        if exc is not None:
            logger.exception("Background pipeline failed for analysis_id=%s", analysis_id, exc_info=exc)

    task.add_done_callback(_on_done)
