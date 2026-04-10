from __future__ import annotations

from datetime import datetime, timezone

from backend.services.news_claim_extractor import extract_news_derived_claims


def test_extract_reddit_style_revenue_and_growth() -> None:
    ho = {
        "sources_active": ["news_api"],
        "news_articles": [
            {
                "source": "Bloomberg",
                "title": "t",
                "date": datetime.now(timezone.utc),
                "content": (
                    "posted a more than 20% rise in revenue in 2023 versus the year before "
                    "and more than $800 million in revenue last year, above the $666 million it saw in 2022"
                ),
                "url": "https://example.com/a",
            }
        ],
    }
    claims = extract_news_derived_claims(ho)
    types = {c.claim_type for c in claims}
    assert "revenue" in types
    assert "growth_rate" in types
    rev_vals = [c.normalized_value for c in claims if c.claim_type == "revenue" and c.normalized_value is not None]
    assert max(rev_vals) >= 800.0


def test_extract_arm_valuation_range_midpoint() -> None:
    ho = {
        "sources_active": ["news_api"],
        "news_articles": [
            {
                "source": "Reuters",
                "title": "t",
                "date": datetime.now(timezone.utc),
                "content": "targeting an IPO at a valuation of between $60 billion and $70 billion",
                "url": "https://example.com/b",
            }
        ],
    }
    claims = extract_news_derived_claims(ho)
    val = next(c.normalized_value for c in claims if c.claim_type == "valuation")
    assert val == 65.0


def test_extract_arm_negative_growth_percent() -> None:
    ho = {
        "sources_active": ["news_api"],
        "news_articles": [
            {
                "source": "Reuters",
                "title": "t",
                "date": datetime.now(timezone.utc),
                "content": "Arm's sales fell to $2.68 billion in the 12 months ended March 31 and fell 1%",
                "url": "https://example.com/c",
            }
        ],
    }
    claims = extract_news_derived_claims(ho)
    growth = [c.normalized_value for c in claims if c.claim_type == "growth_rate"]
    assert any(g == -1.0 for g in growth if g is not None)
