from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class Instrument(BaseModel):
    name: str
    ticker: str | None = None
    rationale_one_liner: str


class Reference(BaseModel):
    id: int
    label: str
    url: str | None = None
    source_hint: str | None = None


class InvestorBrief(BaseModel):
    company_name: str
    sector_theme: str = Field(description="Short sector or theme name")
    primary_instrument: Instrument
    alternates: list[Instrument] = Field(default_factory=list, max_length=2)
    overview_markdown: str = Field(description="Retail tone narrative with inline [1] refs")
    references: list[Reference] = Field(default_factory=list)
    disclaimer_short: str = Field(
        description="Short disclaimer stating this is not investment advice",
        default="This brief is for informational purposes only and does not constitute financial advice. Always conduct your own research.",
    )
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

