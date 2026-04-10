from backend.models.eval_case import EvalDataset


def test_eval_dataset_accepts_text_and_derived_numeric_contradictions() -> None:
    dataset = EvalDataset.model_validate(
        {
            "company_name": "Reddit",
            "cases": [
                {
                    "case_id": "reddit-bloomberg-2024-02-05",
                    "company_name": "Reddit",
                    "article_title": "Bloomberg pre-S-1 revenue leak",
                    "article_published_on": "2024-02-05",
                    "article_source": "Bloomberg",
                    "article_url": "https://www.bloomberg.com/news/articles/2024-02-05/reddit-s-revenue-rises-20-ahead-of-ipo-but-isn-t-profitable-yet",
                    "pre_ipo_news_excerpt": "posted a more than 20% rise in revenue in 2023 versus the year before and more than $800 million in revenue last year, above the $666 million it saw in 2022",
                    "filing_type": "S-1",
                    "filing_url": "https://www.sec.gov/Archives/edgar/data/1713445/000162828024006294/reddits-1q423.htm",
                    "filing_excerpt": "Our revenue for the years ended December 31, 2022 and 2023 was $666.7 million and $804.0 million, respectively, representing growth of 21%.",
                    "expected_label": "no_contradiction",
                    "claims_to_extract": [
                        {
                            "claim_id": "revenue_2023",
                            "claim_type": "revenue",
                            "claim_text": "2023 revenue was more than $800 million",
                            "claim_value": 804.0,
                            "claim_unit": "usd_millions",
                            "claim_period": "2023",
                            "comparison_mode": "approximate_match",
                        },
                        {
                            "claim_id": "revenue_growth_2023",
                            "claim_type": "growth_rate",
                            "claim_text": "2023 revenue rose more than 20% from 2022",
                            "claim_value": 21.0,
                            "claim_unit": "percent",
                            "claim_period": "2023_vs_2022",
                            "comparison_mode": "approximate_match",
                        },
                    ],
                },
                {
                    "case_id": "reddit-marketwatch-2024-03-11",
                    "company_name": "Reddit",
                    "article_title": "MarketWatch valuation mismatch",
                    "article_published_on": "2024-03-11",
                    "article_source": "MarketWatch",
                    "article_url": "https://www.marketwatch.com/story/reddit-launches-ipo-at-a-valuation-of-up-to-5-5-billion-e062fed1",
                    "pre_ipo_news_excerpt": "Reddit launches IPO at a valuation of up to $5.5 billion",
                    "filing_type": "424B4",
                    "filing_url": "https://www.sec.gov/Archives/edgar/data/1713445/000162828024012380/reddit-final424b4.htm",
                    "filing_excerpt": "The initial public offering price per share of our Class A common stock is $34.00. Total $748,000,000.",
                    "expected_label": "contradiction",
                    "claims_to_extract": [
                        {
                            "claim_id": "valuation_target",
                            "claim_type": "valuation",
                            "claim_text": "IPO valuation up to $5.5 billion",
                            "claim_value": 5.5,
                            "claim_unit": "usd_billions",
                            "comparison_mode": "derived_numeric_check",
                        }
                    ],
                    "contradictions": [
                        {
                            "contradiction_id": "valuation_math_mismatch",
                            "contradiction_type": "derived_numeric_contradiction",
                            "claim_id": "valuation_target",
                            "contradicted_claim_text": "IPO valuation up to $5.5 billion",
                            "filing_proof_text": "The initial public offering price per share of our Class A common stock is $34.00. Total $748,000,000.",
                            "derived_inputs": {
                                "offering_price_per_share": 34.0,
                                "gross_proceeds_usd_millions": 748.0,
                                "implied_equity_value_usd_billions": 6.4,
                            },
                            "derived_output_value": 6.4,
                            "derived_output_unit": "usd_billions",
                        }
                    ],
                },
            ]
        }
    )

    assert dataset.schema_version == "1.0"
    assert len(dataset.cases) == 2
    assert dataset.cases[0].expected_label == "no_contradiction"
    assert dataset.cases[1].contradictions[0].contradiction_type == "derived_numeric_contradiction"
