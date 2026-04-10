from typing import Literal

from pydantic import BaseModel, Field


ClaimType = Literal[
    "revenue",
    "ad_revenue",
    "growth_rate",
    "net_loss",
    "valuation",
    "share_count",
    "proceeds",
    "offering_price_range",
    "other",
]

ComparisonMode = Literal[
    "exact_match",
    "approximate_match",
    "floor_claim",
    "derived_numeric_check",
]

EvalLabel = Literal["contradiction", "no_contradiction"]
ContradictionType = Literal["text_contradiction", "derived_numeric_contradiction"]


class EvalClaim(BaseModel):
    claim_id: str
    claim_type: ClaimType
    claim_text: str
    claim_value: float | None = None
    claim_unit: str | None = None
    claim_period: str | None = None
    comparison_mode: ComparisonMode = "exact_match"
    source_excerpt: str | None = None


class EvalContradiction(BaseModel):
    contradiction_id: str
    contradiction_type: ContradictionType
    claim_id: str
    contradicted_claim_text: str
    filing_proof_text: str
    expected_label: EvalLabel = "contradiction"
    derived_inputs: dict[str, float] = Field(default_factory=dict)
    derived_output_value: float | None = None
    derived_output_unit: str | None = None


class EvalCase(BaseModel):
    case_id: str
    company_name: str
    article_title: str
    article_published_on: str | None = None
    article_source: str
    article_url: str
    pre_ipo_news_excerpt: str
    filing_type: Literal["S-1", "424B4", "S-1_and_424B4", "other"]
    filing_url: str | None = None
    filing_excerpt: str
    post_ipo_filing_excerpt: str | None = None
    expected_label: EvalLabel
    claims_to_extract: list[EvalClaim] = Field(default_factory=list)
    contradictions: list[EvalContradiction] = Field(default_factory=list)


class EvalDataset(BaseModel):
    schema_version: str = "1.0"
    company_name: str
    cases: list[EvalCase] = Field(default_factory=list)
