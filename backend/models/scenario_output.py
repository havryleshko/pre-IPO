from datetime import datetime
from pydantic import BaseModel, Field

from backend.models.analysis import AnalysisComplexityTier


class PriceTargets(BaseModel):
    days_30: float = Field(alias="30_days")
    days_90: float = Field(alias="90_days")
    year_1: float = Field(alias="1_year")


class ScenarioDetails(BaseModel):
    probability: float
    drivers: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    price_targets: PriceTargets
    weighting_rationale: str
    rules_applied: list[str] = Field(default_factory=list)


class ScenarioSet(BaseModel):
    pessimistic: ScenarioDetails
    realistic: ScenarioDetails
    optimistic: ScenarioDetails


class ScenarioOutput(BaseModel):
    company_name: str
    complexity_tier: AnalysisComplexityTier
    scenarios: ScenarioSet
    probability_sum_check: float
    llm_adjustment_applied: bool
    llm_adjustment_rationale: str | None = None
    built_at: datetime
