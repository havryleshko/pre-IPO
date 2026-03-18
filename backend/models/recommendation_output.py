from datetime import datetime
from typing import Literal

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
    decision: Literal["buy", "watch", "avoid"] | None = None
    decision_scope: Literal["pre_ipo_fund", "post_ipo_direct", "no_trade"] | None = None
    entry_triggers: list[str] = Field(default_factory=list)
    watch_triggers: list[str] = Field(default_factory=list)
    kill_criteria: list[str] = Field(default_factory=list)
    sizing_guidance: str = ""
    decision_rationale: str = ""
    decision_evidence: list[str] = Field(default_factory=list)
    pre_ipo_beneficiary_funds: PreIpoBeneficiaryFunds
    recommendations: Recommendations
    plain_english_summary: str
    investment_action: str = ""
    funds_to_consider: list[str] = Field(default_factory=list)
    what_to_watch: list[str] = Field(default_factory=list)
    generated_at: datetime
