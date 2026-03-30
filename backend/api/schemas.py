from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
from backend.models.analysis import AnalysisComplexityTier, AnalysisStatus
from backend.models.single_agent_result import SingleAgentResult


class CreateAnalysisRequest(BaseModel):
    company_name: str


class CreateAnalysisResponse(BaseModel):
    analysis_id: UUID
    company_name: str
    status: AnalysisStatus = "pending"
    complexity_tier: AnalysisComplexityTier = "standard"
    created_at: datetime


class AnalysisOutputsResponse(BaseModel):
    analysis_id: UUID
    company_name: str
    status: AnalysisStatus
    complexity_tier: AnalysisComplexityTier
    last_completed_agent: str | None = None
    created_at: datetime
    analysis_result: SingleAgentResult | None = None
