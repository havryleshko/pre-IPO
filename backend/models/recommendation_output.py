from datetime import datetime

from pydantic import BaseModel, Field


class ScenarioRecommendation(BaseModel):
    recommended_positioning: str
    conviction: str
    rationale: str
    risk_warning: str
    client_paragraph: str


class Recommendations(BaseModel):
    pessimistic: ScenarioRecommendation
    realistic: ScenarioRecommendation
    optimistic: ScenarioRecommendation


class BeneficiaryFundCandidate(BaseModel):
    fund_name: str
    confidence: str
    relation_type: str
    evidence: list[str] = Field(default_factory=list)


class PreIpoBeneficiaryFunds(BaseModel):
    candidates: list[BeneficiaryFundCandidate] = Field(default_factory=list)
    methodology: str


class RecommendationOutput(BaseModel):
    company_name: str
    pre_ipo_beneficiary_funds: PreIpoBeneficiaryFunds
    recommendations: Recommendations
    plain_english_summary: str
    generated_at: datetime
