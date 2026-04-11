from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreateAnalysisResponse(BaseModel):
    analysis_id: str
    company_name: str
    status: str
    complexity_tier: str
    created_at: datetime


class ProgressEvent(BaseModel):
    type: Literal["agent_status"]
    agent_name: str
    status: str
    tool_call: str | None = None


class PredictionClaim(BaseModel):
    claim_id: str
    claim_type: str
    prediction_text: str
    source: str
    source_url: str | None = None
    published_at: datetime | None = None


class FilingFact(BaseModel):
    fact_id: str
    metric: str
    value: float | None = None
    units: str | None = None
    source: str
    source_reference: str | None = None
    source_url: str | None = None


class OutcomeMetrics(BaseModel):
    ipo_price: float | None = None
    current_price: float | None = None
    performance_since_ipo_pct: float | None = None
    peak_price: float | None = None
    trough_price: float | None = None
    lock_up_cliff_date: str | None = None
    price_at_lock_up_cliff: float | None = None


class ClaimCheck(BaseModel):
    claim_id: str
    status: Literal["supported", "missed", "mixed", "unverifiable"]
    matched_facts: list[str] = Field(default_factory=list)
    evidence_quotes: list[str] = Field(default_factory=list)
    rationale: str | None = None
    confidence: Literal["high", "medium", "low"] = "medium"


class PatternFlag(BaseModel):
    signal: str
    was_visible_at_ipo: bool
    outcome: str


class NarrativeReport(BaseModel):
    headline: str
    pre_ipo_story: list[str]
    post_ipo_grounding: list[str]
    key_differences: list[str]
    watch_items: list[str]
    sources_cited: list[str]


class NewsDerivedClaim(BaseModel):
    claim_id: str
    claim_type: str
    normalized_value: float | None = None
    units: str | None = None
    period: str | None = None
    source: str
    evidence_quote: str
    article_url: str
    published_at: datetime | None = None


class NewsFilingDiscrepancy(BaseModel):
    discrepancy_id: str
    news_claim_id: str
    contradiction_type: str
    news_evidence: str
    filing_evidence: str
    derived_value_filing: float | None = None
    derived_value_news: float | None = None


class SingleAgentResult(BaseModel):
    company_name: str
    generated_at: datetime
    prediction_claims: list[PredictionClaim] = Field(default_factory=list)
    filing_facts: list[FilingFact] = Field(default_factory=list)
    outcome_metrics: OutcomeMetrics | None = None
    claim_checks: list[ClaimCheck] = Field(default_factory=list)
    patterns: list[PatternFlag] = Field(default_factory=list)
    narrative: NarrativeReport | None = None
    news_derived_claims: list[NewsDerivedClaim] = Field(default_factory=list)
    news_filing_discrepancies: list[NewsFilingDiscrepancy] = Field(default_factory=list)


class AnalysisOutputsResponse(BaseModel):
    analysis_id: str
    company_name: str
    status: str
    complexity_tier: str
    last_completed_agent: str | None = None
    created_at: datetime
    analysis_result: SingleAgentResult | None = None

