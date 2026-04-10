from __future__ import annotations

from backend.models.single_agent_result import NewsDerivedClaim
from backend.services.news_filing_discrepancy import build_news_filing_discrepancies


def test_valuation_discrepancy_arm_style() -> None:
    news = [
        NewsDerivedClaim(
            claim_id="n1",
            claim_type="valuation",
            normalized_value=65.0,
            units="usd_billions",
            period=None,
            source="news_api",
            evidence_quote="between $60 billion and $70 billion",
            article_url="u",
            published_at=None,
        )
    ]
    filing = (
        "The initial public offering price per ADS is $51.00 for 95,500,000 American Depositary Shares. "
        "Total $4,870,500,000."
    )
    discs = build_news_filing_discrepancies(news, {}, {}, filing)
    assert len(discs) == 1
    assert discs[0].contradiction_type == "derived_numeric_contradiction"
    assert discs[0].derived_value_filing is not None
    assert abs(float(discs[0].derived_value_filing) - 54.5) < 0.01


def test_revenue_no_discrepancy_when_filing_matches_one_year() -> None:
    news = [
        NewsDerivedClaim(
            claim_id="r1",
            claim_type="revenue",
            normalized_value=804.0,
            units="usd_millions",
            period=None,
            source="news_api",
            evidence_quote="$804 million",
            article_url="u",
            published_at=None,
        )
    ]
    filing = "Our revenue for the years ended December 31, 2022 and 2023 was $666.7 million and $804.0 million"
    parser = {"financials": {"revenue": 804_000_000.0}}
    discs = build_news_filing_discrepancies(news, parser, {}, filing)
    assert discs == []
