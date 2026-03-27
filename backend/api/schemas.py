from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
from backend.models.analysis import AnalysisComplexityTier, AnalysisStatus
from backend.models.harvester_output import HarvesterOutput
from backend.models.parser_output import ParserOutput
from backend.models.scenario_output import ScenarioOutput
from backend.models.investor_brief import InvestorBrief


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
    harvester_output: HarvesterOutput | None = None
    parser_output: ParserOutput | None = None
    scenario_output: ScenarioOutput | None = None
    investor_brief: InvestorBrief | None = None
