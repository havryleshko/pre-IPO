import importlib
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
    set_ifa_confirmed_flags,
)

router = APIRouter(prefix="/analyses", tags=["analysis"])


class ConfirmFlagsRequest(BaseModel):
    flag_ids: list[str] = Field(default_factory=list)


class ConfirmFlagsResponse(BaseModel):
    analysis_id: str
    ifa_confirmed_flags: list[str] = Field(default_factory=list)
    export_locked: bool


class _CreateAnalysisState(TypedDict):
    company_name: str
    analysis_record: dict[str, Any] | None


class _ConfirmFlagsState(TypedDict):
    analysis_id: str
    submitted_flag_ids: list[str]
    ifa_confirmed_flags: list[str]
    export_locked: bool


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
            "export_locked": record.get("export_locked", True),
            "created_at": record["created_at"],
            "harvester_output": record.get("harvester_output"),
            "parser_output": record.get("parser_output"),
            "scenario_output": record.get("scenario_output"),
            "recommendation_output": record.get("recommendation_output"),
            "judge_output": record.get("judge_output"),
            "flags": record.get("flags") or [],
        }
    )


@router.post("/{analysis_id}/confirm-flags", response_model=ConfirmFlagsResponse)
async def confirm_flags_endpoint(
    analysis_id: str,
    payload: ConfirmFlagsRequest,
) -> ConfirmFlagsResponse:
    analysis = await get_analysis_by_id(analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    flags = list(dict(analysis).get("flags") or [])
    available_flag_ids = {
        str(item.get("flag_id"))
        for item in flags
        if isinstance(item, dict) and item.get("flag_id") is not None
    }
    submitted = set(payload.flag_ids)
    unknown_flags = sorted(submitted - available_flag_ids)
    if unknown_flags:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown flag IDs: {', '.join(unknown_flags)}",
        )

    existing_confirmed = {
        str(value)
        for value in (dict(analysis).get("ifa_confirmed_flags") or [])
    }
    graph = _build_confirm_flags_graph(available_flag_ids=available_flag_ids)
    final_state = await graph.ainvoke(
        {
            "analysis_id": analysis_id,
            "submitted_flag_ids": sorted(submitted | existing_confirmed),
            "ifa_confirmed_flags": [],
            "export_locked": True,
        }
    )
    await set_ifa_confirmed_flags(
        analysis_id=analysis_id,
        confirmed_flags=final_state["ifa_confirmed_flags"],
        export_locked=final_state["export_locked"],
    )
    return ConfirmFlagsResponse(
        analysis_id=analysis_id,
        ifa_confirmed_flags=final_state["ifa_confirmed_flags"],
        export_locked=final_state["export_locked"],
    )


def _build_create_analysis_graph() -> Any:
    state_graph_cls, start_node, end_node = _load_langgraph_graph_components()
    graph_builder = state_graph_cls(_CreateAnalysisState)
    graph_builder.add_node("persist_analysis", _persist_analysis_node)
    graph_builder.add_edge(start_node, "persist_analysis")
    graph_builder.add_edge("persist_analysis", end_node)
    return graph_builder.compile()


def _build_confirm_flags_graph(available_flag_ids: set[str]) -> Any:
    async def _resolve_confirmations(state: _ConfirmFlagsState) -> _ConfirmFlagsState:
        confirmed = sorted(set(state["submitted_flag_ids"]))
        missing = available_flag_ids - set(confirmed)
        return {
            "analysis_id": state["analysis_id"],
            "submitted_flag_ids": state["submitted_flag_ids"],
            "ifa_confirmed_flags": confirmed,
            "export_locked": len(missing) > 0,
        }

    state_graph_cls, start_node, end_node = _load_langgraph_graph_components()
    graph_builder = state_graph_cls(_ConfirmFlagsState)
    graph_builder.add_node("resolve_confirmations", _resolve_confirmations)
    graph_builder.add_edge(start_node, "resolve_confirmations")
    graph_builder.add_edge("resolve_confirmations", end_node)
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
