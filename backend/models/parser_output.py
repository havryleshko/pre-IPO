from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FactualClaimEvidence(BaseModel):
    source: str
    source_reference: str
    url: str | None = None
    quote: str | None = None
    confidence: Literal["high", "medium", "low"] = "medium"
    extracted_at: datetime | None = None


class RiskFactorClaimEvidence(BaseModel):
    risk_factor: str
    source: str
    source_reference: str
    url: str | None = None
    quote: str | None = None
    confidence: Literal["high", "medium", "low"] = "medium"
    extracted_at: datetime | None = None


class Financials(BaseModel):
    revenue: float | None = None
    revenue_evidence: FactualClaimEvidence | None = None
    revenue_growth_yoy: float | None = None
    revenue_growth_yoy_evidence: FactualClaimEvidence | None = None
    burn_rate_monthly: float | None = None
    burn_rate_monthly_evidence: FactualClaimEvidence | None = None
    cash_runway_months: float | None = None
    cash_runway_months_evidence: FactualClaimEvidence | None = None


class KeyPerson(BaseModel):
    name: str
    role: str
    background: str


class ComparableValuation(BaseModel):
    company: str
    metric: str
    value: float


class FloatDetails(BaseModel):
    total_shares_offered: float
    total_shares_offered_evidence: FactualClaimEvidence | None = None
    insider_shares: float
    insider_shares_evidence: FactualClaimEvidence | None = None
    public_float: float
    public_float_evidence: FactualClaimEvidence | None = None
    greenshoe_option: bool


class DemandSignals(BaseModel):
    anchor_investors: list[str] = Field(default_factory=list)
    institutional_interest: Literal["high", "medium", "low", "unknown"]
    roadshow_sentiment: str


class FundingHistoryItem(BaseModel):
    round: str
    amount: float
    date: datetime
    investors: list[str] = Field(default_factory=list)
    valuation: float | None = None


class FlaggedSection(BaseModel):
    section: str
    reason: str
    verify_at: str


class ParserOutput(BaseModel):
    company_name: str
    business_model: str
    financials: Financials
    risk_factors: list[str] = Field(default_factory=list, max_length=10)
    risk_factors_evidence: list[RiskFactorClaimEvidence] = Field(
        default_factory=list, max_length=10
    )
    use_of_proceeds: str
    use_of_proceeds_evidence: FactualClaimEvidence | None = None
    key_people: list[KeyPerson] = Field(default_factory=list)
    comparable_valuations: list[ComparableValuation] = Field(default_factory=list)
    lockup_period_days: int
    lockup_period_days_evidence: FactualClaimEvidence | None = None
    float_details: FloatDetails
    demand_signals: DemandSignals
    funding_history: list[FundingHistoryItem] = Field(default_factory=list)
    offering_type: Literal["primary", "secondary", "mixed"]
    insider_selling_percentage: float | None = None
    insider_selling_percentage_evidence: FactualClaimEvidence | None = None
    parsed_at: datetime
    data_confidence: Literal["high", "medium", "low"]
    flagged_sections: list[FlaggedSection] = Field(default_factory=list)
