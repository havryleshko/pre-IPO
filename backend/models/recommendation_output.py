from datetime import datetime

from pydantic import BaseModel


class ScenarioRecommendation(BaseModel):
    etf_ticker: str
    etf_name: str
    etf_verified_active: bool
    rationale: str
    risk_warning: str
    client_paragraph: str


class Recommendations(BaseModel):
    pessimistic: ScenarioRecommendation
    realistic: ScenarioRecommendation
    optimistic: ScenarioRecommendation


class RecommendationOutput(BaseModel):
    company_name: str
    recommendations: Recommendations
    plain_english_summary: str
    generated_at: datetime
