from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Financials(BaseModel):
    revenue: float | None = None
    revenue_growth_yoy: float | None = None
    burn_rate_monthly: float | None = None
    cash_runway_months: float | None = None


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
    insider_shares: float
    public_float: float
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
    use_of_proceeds: str
    key_people: list[KeyPerson] = Field(default_factory=list)
    comparable_valuations: list[ComparableValuation] = Field(default_factory=list)
    lockup_period_days: int
    float_details: FloatDetails
    demand_signals: DemandSignals
    funding_history: list[FundingHistoryItem] = Field(default_factory=list)
    offering_type: Literal["primary", "secondary", "mixed"]
    insider_selling_percentage: float | None = None
    parsed_at: datetime
    data_confidence: Literal["high", "medium", "low"]
    flagged_sections: list[FlaggedSection] = Field(default_factory=list)
