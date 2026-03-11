from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

AnalysisComplexityTier = Literal["simple", "standard", "complex"]
AnalysisStatus = Literal["pending", "running", "completed", "failed"]


class AnalysisCreate(BaseModel):
    company_name: str
    custom_name: str | None = None
    complexity_tier: AnalysisComplexityTier = "standard"


class AnalysisStatusUpdate(BaseModel):
    status: AnalysisStatus
    last_completed_agent: str | None = None


class AnalysisRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    custom_name: str | None = None
    company_name: str
    complexity_tier: AnalysisComplexityTier = "standard"
    status: AnalysisStatus = "pending"
    last_completed_agent: str | None = None
    lead_plan: dict[str, Any] | None = None
    harvester_output: dict[str, Any] | None = None
    parser_output: dict[str, Any] | None = None
    scenario_output: dict[str, Any] | None = None
    recommendation_output: dict[str, Any] | None = None
    judge_output: dict[str, Any] | None = None
    final_report: dict[str, Any] | None = None
    flags: list[dict[str, Any]] | None = None
    ifa_confirmed_flags: list[str] | None = None
    export_locked: bool = True
    created_at: datetime
    saved: bool = False
    saved_at: datetime | None = None
