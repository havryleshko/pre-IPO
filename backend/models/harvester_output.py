from datetime import datetime
from typing import Any

from pydantic import BaseModel

from backend.models.analysis import AnalysisComplexityTier


class SecFiling(BaseModel):
    url: str
    text: str
    filing_type: str


class NewsArticle(BaseModel):
    source: str
    title: str
    date: datetime
    content: str
    url: str
    is_primary_source: bool


class CrunchbaseData(BaseModel):
    total_raised: float | None = None
    funding_rounds: list[dict[str, Any]] = []
    investors: list[str] = []
    last_valuation: float | None = None


class YahooFinanceData(BaseModel):
    comparable_companies: list[str] = []
    sector_multiples: dict[str, Any] = {}
    sector_90d_performance: float | None = None


class FredData(BaseModel):
    fed_funds_rate: float | None = None
    market_conditions: str | None = None
    retrieved_at: datetime | None = None


class TwitterSentimentScore(BaseModel):
    positive: float
    negative: float
    neutral: float


class TwitterQuote(BaseModel):
    author: str
    role: str
    quote: str
    date: datetime
    url: str


class TwitterData(BaseModel):
    sentiment_score: TwitterSentimentScore
    key_quotes: list[TwitterQuote] = []


class SourceFailure(BaseModel):
    source: str
    reason: str


class HarvesterOutput(BaseModel):
    company_name: str
    complexity_tier: AnalysisComplexityTier
    sec_filings: list[SecFiling] = []
    news_articles: list[NewsArticle] = []
    crunchbase_data: CrunchbaseData
    yahoo_finance_data: YahooFinanceData
    fred_data: FredData
    twitter_data: TwitterData | None = None
    sources_active: list[str] = []
    sources_failed: list[SourceFailure] = []
    harvested_at: datetime
