from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.models.scenario_output import PatternFlag


class PredictionClaim(BaseModel):
    claim_id: str
    claim_type: Literal[
        "valuation",
        "demand",
        "growth",
        "margin",
        "burn",
        "runway",
        "insider_selling",
        "lockup",
        "other",
    ]
    prediction_text: str
    source: str
    source_url: str | None = None
    published_at: datetime | None = None


class FilingFact(BaseModel):
    fact_id: str
    metric: str
    value: float | None = None
    units: str | None = None
    source: Literal["s1_f1", "post_ipo_filing", "other"]
    source_reference: str | None = None
    source_url: str | None = None


class OutcomeMetrics(BaseModel):
    ipo_price: float | None = None
    current_price: float | None = None
    performance_since_ipo_pct: float | None = None
    peak_price: float | None = None
    trough_price: float | None = None
    lock_up_cliff_date: date | None = None
    price_at_lock_up_cliff: float | None = None


class ClaimCheck(BaseModel):
    claim_id: str
    status: Literal["supported", "missed", "mixed", "unverifiable"]
    matched_facts: list[str] = Field(default_factory=list)
    evidence_quotes: list[str] = Field(default_factory=list)
    rationale: str | None = None
    confidence: Literal["high", "medium", "low"] = "medium"


class SingleAgentResult(BaseModel):
    company_name: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    prediction_claims: list[PredictionClaim] = Field(default_factory=list)
    filing_facts: list[FilingFact] = Field(default_factory=list)
    outcome_metrics: OutcomeMetrics | None = None
    claim_checks: list[ClaimCheck] = Field(default_factory=list)
    patterns: list[PatternFlag] = Field(default_factory=list)

