from datetime import date, datetime
from typing import Literal
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


class DeliveryEvidence(BaseModel):
    claim: str
    actual: str
    verdict: Literal["met", "missed", "exceeded"]


class PricePerformance(BaseModel):
    ipo_price: float | None = None
    current_price: float | None = None
    peak_price: float | None = None
    trough_price: float | None = None
    performance_since_ipo_pct: float | None = None
    lock_up_cliff_date: date | None = None
    price_at_lock_up_cliff: float | None = None


class PatternFlag(BaseModel):
    signal: str
    was_visible_at_ipo: bool
    outcome: str


class ScenarioOutput(BaseModel):
    company_name: str
    complexity_tier: AnalysisComplexityTier
    scenarios: ScenarioSet
    probability_sum_check: float
    llm_adjustment_applied: bool
    llm_adjustment_rationale: str | None = None
    ipo_delivery_verdict: Literal["delivered", "underdelivered", "mixed"] | None = None
    delivery_score: float | None = None
    delivery_evidence: list[DeliveryEvidence] = Field(default_factory=list)
    price_performance: PricePerformance | None = None
    patterns_flagged: list[PatternFlag] = Field(default_factory=list)
    built_at: datetime
