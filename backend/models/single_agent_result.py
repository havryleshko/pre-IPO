from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.models.eval_case import ClaimType, ContradictionType
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
    peak_date: date | None = None
    trough_price: float | None = None
    trough_date: date | None = None
    lock_up_cliff_date: date | None = None
    price_at_lock_up_cliff: float | None = None
    recovered_to_ipo_date: date | None = None
    recovered_to_peak_date: date | None = None


class CompanyProfile(BaseModel):
    issuer_name: str
    ticker: str | None = None
    company_ticker: str
    industry_region: str
    ipo_date: date | None = None
    listing_type: str | None = None


class PreIpoThesis(BaseModel):
    key_pre_ipo_claims: list[str] = Field(default_factory=list)
    source_document_types: list[str] = Field(default_factory=list)
    source_excerpts: list[str] = Field(default_factory=list)


class RealizedOutcome(BaseModel):
    long_term_outcome: str
    forecast_error: str


class PatternClassification(BaseModel):
    primary_pattern_id: int | None = None
    primary_pattern_label: str
    confidence: Literal["high", "medium", "low"] = "medium"
    rationale: str | None = None
    analog_companies: list[str] = Field(default_factory=list)
    secondary_pattern_labels: list[str] = Field(default_factory=list)
    source: Literal["reference_exact", "reference_analog", "heuristic"] = "heuristic"


class ReferenceTableRow(BaseModel):
    company_ticker: str
    industry_region: str
    ipo_date: str
    key_pre_ipo_claims: str
    long_term_outcome: str
    forecast_error: str
    predicted_pattern: str


class ClaimCheck(BaseModel):
    claim_id: str
    status: Literal["supported", "missed", "mixed", "unverifiable"]
    matched_facts: list[str] = Field(default_factory=list)
    evidence_quotes: list[str] = Field(default_factory=list)
    rationale: str | None = None
    confidence: Literal["high", "medium", "low"] = "medium"


class NarrativeReport(BaseModel):
    headline: str
    pre_ipo_story: list[str]
    post_ipo_grounding: list[str]
    key_differences: list[str]
    watch_items: list[str]
    sources_cited: list[str]


class NewsDerivedClaim(BaseModel):
    claim_id: str
    claim_type: ClaimType
    normalized_value: float | None = None
    units: str | None = None
    period: str | None = None
    source: Literal["news_api", "rss"]
    evidence_quote: str
    article_url: str
    published_at: datetime | None = None


class NewsFilingDiscrepancy(BaseModel):
    discrepancy_id: str
    news_claim_id: str
    contradiction_type: ContradictionType
    news_evidence: str
    filing_evidence: str
    derived_value_filing: float | None = None
    derived_value_news: float | None = None


class SingleAgentResult(BaseModel):
    company_name: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    prediction_claims: list[PredictionClaim] = Field(default_factory=list)
    filing_facts: list[FilingFact] = Field(default_factory=list)
    outcome_metrics: OutcomeMetrics | None = None
    company_profile: CompanyProfile | None = None
    pre_ipo_thesis: PreIpoThesis | None = None
    realized_outcome: RealizedOutcome | None = None
    pattern_classification: PatternClassification | None = None
    reference_table_row: ReferenceTableRow | None = None
    claim_checks: list[ClaimCheck] = Field(default_factory=list)
    patterns: list[PatternFlag] = Field(default_factory=list)
    narrative: NarrativeReport | None = None
    news_derived_claims: list[NewsDerivedClaim] = Field(default_factory=list)
    news_filing_discrepancies: list[NewsFilingDiscrepancy] = Field(default_factory=list)

