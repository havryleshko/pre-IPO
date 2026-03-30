import asyncio
import logging
from typing import Any

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

@router.post("", response_model=CreateAnalysisResponse)
async def create_analysis_endpoint(payload: CreateAnalysisRequest) -> CreateAnalysisResponse:
    record = await create_analysis(company_name=payload.company_name)
    if record is None:
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
            "analysis_result": record.get("final_report"),
        }
    )


def _schedule_pipeline(analysis_id: str) -> None:
    task = asyncio.create_task(run_analysis_pipeline(analysis_id))

    def _on_done(completed_task: asyncio.Task[None]) -> None:
        exc = completed_task.exception()
        if exc is not None:
            logger.exception("Background pipeline failed for analysis_id=%s", analysis_id, exc_info=exc)

    task.add_done_callback(_on_done)
