import pytest
from types import SimpleNamespace
from unittest.mock import patch

from backend.agents.complexity_classifier import (
    ComplexityClassifierInput,
    classify_complexity,
)
from tests.integration.pipeline_e2e_harness import (
    PipelineE2EParams,
    assert_single_agent_pipeline_json_outputs,
    run_full_pipeline_e2e,
)
from backend.models.harvester_output import SecFiling

SAMPLE_S1 = """
Total revenue for the year was $1,500 million. Cash used in operating activities was $50 million per month.
Cash runway 18 months. The 180 days lock-up period applies to insiders.
Total shares offered 100,000,000. Public float 70,000,000.
"""


ARM_DELIVERED_S1 = """
Our business model focuses on semiconductor IP licensing.
Total revenue for the year was $2,800 million. Year-over-year growth of 45%.
Cash used in operating activities was $50 million per month. Cash runway 18 months.
We intend to use the net proceeds from this offering for capital expenditures.
The 180 days lock-up period applies to insiders.
Total shares offered 100,000,000. Shares by existing stockholders 30,000,000.
Public float 70,000,000. The underwriters have an over-allotment option.
Strong institutional interest. The roadshow was oversubscribed.
"""

ARM_DELIVERED_10K = """
Form 10-K Annual Report
ITEM 1A. RISK FACTORS
Our business faces material risks because market conditions remain uncertain and could adversely affect our semiconductor licensing revenue and competitive position over the long term.
Another material risk is that geopolitical tensions could disrupt supply chains and increase operational costs materially beyond our current forecasts in ways we cannot fully predict today.
A third risk is that increased competition from larger technology companies could reduce pricing power and erode margins in key growth segments we target globally.
A fourth risk relates to intellectual property challenges that may arise from litigation or regulatory actions in multiple jurisdictions simultaneously.
A fifth risk is that reliance on a concentrated set of customers could amplify revenue volatility if demand shifts unexpectedly in the smartphone and automotive end markets.
We may also face a sixth category of risks from foreign exchange fluctuations that are not fully hedged in our current treasury policies.

MANAGEMENT'S DISCUSSION AND ANALYSIS
Consolidated Statements of Operations. Total revenue was $2.8 billion for the year ended December 31, 2024.
Cash used in operating activities was $600 million for the year ended December 31, 2024.
"""

CART_UNDERDELIVERED_S1 = """
Our business model focuses on grocery delivery technology.
Total revenue for the year was $3,000 million. Year-over-year growth of 30%.
Cash used in operating activities was $50 million per month. Cash runway 14 months.
We intend to use the net proceeds from this offering for capital expenditures.
The 180 days lock-up period applies to insiders.
Total shares offered 100,000,000. Shares by existing stockholders 25,000,000.
Public float 75,000,000. The underwriters have an over-allotment option.
Strong institutional interest. The roadshow was oversubscribed.
"""

CART_UNDERDELIVERED_10K = """
Form 10-K Annual Report
ITEM 1A. RISK FACTORS
Our business faces material risks because market conditions remain uncertain and could adversely affect our grocery delivery revenue and competitive position over the long term.
Another material risk is that geopolitical tensions could disrupt supply chains and increase operational costs materially beyond our current forecasts in ways we cannot fully predict today.
A third risk is that increased competition from larger technology companies could reduce pricing power and erode margins in key growth segments we target globally.
A fourth risk relates to intellectual property challenges that may arise from litigation or regulatory actions in multiple jurisdictions simultaneously.
A fifth risk is that reliance on a concentrated set of customers could amplify revenue volatility if demand shifts unexpectedly.
We may also face a sixth category of risks from foreign exchange fluctuations that are not fully hedged in our current treasury policies.

MANAGEMENT'S DISCUSSION AND ANALYSIS
Consolidated Statements of Operations. Total revenue was $2.4 billion for the year ended December 31, 2024.
Cash used in operating activities was $600 million for the year ended December 31, 2024.
"""


async def _mock_sec_edgar_happy(company_name: str) -> list[SecFiling]:
    return [SecFiling(url="https://sec.gov/1", text=SAMPLE_S1, filing_type="S-1")]


async def _mock_sec_edgar_arm(company_name: str) -> list[SecFiling]:
    return [
        SecFiling(url="https://sec.gov/arm-s1", text=ARM_DELIVERED_S1, filing_type="S-1"),
        SecFiling(url="https://sec.gov/arm-10k", text=ARM_DELIVERED_10K, filing_type="10-K"),
    ]


async def _mock_sec_edgar_cart(company_name: str) -> list[SecFiling]:
    return [
        SecFiling(url="https://sec.gov/cart-s1", text=CART_UNDERDELIVERED_S1, filing_type="S-1"),
        SecFiling(url="https://sec.gov/cart-10k", text=CART_UNDERDELIVERED_10K, filing_type="10-K"),
    ]


def _ipo_history_positive() -> dict:
    return {
        "ipo_price": 50.0,
        "current_price": 55.0,
        "peak_price": 60.0,
        "peak_date": "2023-10-10",
        "trough_price": 45.0,
        "trough_date": "2023-09-20",
        "performance_since_ipo_pct": 10.0,
        "lock_up_cliff_date": None,
        "price_at_lock_up_cliff": 52.0,
        "recovered_to_ipo_date": "2023-10-01",
        "recovered_to_peak_date": "2023-10-10",
    }


def _ipo_history_cart() -> dict:
    return {
        "ipo_price": 30.0,
        "current_price": 22.0,
        "peak_price": 35.0,
        "peak_date": "2023-09-20",
        "trough_price": 20.0,
        "trough_date": "2023-12-01",
        "performance_since_ipo_pct": -20.0,
        "lock_up_cliff_date": None,
        "price_at_lock_up_cliff": 24.0,
        "recovered_to_ipo_date": None,
        "recovered_to_peak_date": None,
    }


@pytest.mark.asyncio
async def test_full_pipeline_happy_path_produces_three_scenarios() -> None:
    store = await run_full_pipeline_e2e(
        PipelineE2EParams(
            company_name="TestCo",
            mock_sec_edgar=_mock_sec_edgar_happy,
            ipo_price_history=_ipo_history_positive(),
            investor_brief_overrides={"ipo_verdict": "mixed"},
        )
    )
    expected_classifier = classify_complexity(
        ComplexityClassifierInput(
            company_name=store["company_name"],
            has_s1_filed=False,
            media_coverage_score=0,
            source_count_hint=5,
        )
    )
    assert store["complexity_tier"] == expected_classifier.complexity_tier
    scenario_output = store.get("scenario_output")
    assert scenario_output is not None
    scenarios = scenario_output.get("scenarios")
    assert isinstance(scenarios, dict)
    assert "pessimistic" in scenarios
    assert "realistic" in scenarios
    assert "optimistic" in scenarios

    final_report = store.get("final_report")
    assert isinstance(final_report, dict)
    assert "prediction_claims" in final_report
    assert "filing_facts" in final_report
    assert "outcome_metrics" in final_report
    assert "company_profile" in final_report
    assert "reference_table_row" in final_report
    assert "ipo_projection" in final_report
    assert "claim_checks" in final_report
    assert "patterns" in final_report
    outcome = final_report["outcome_metrics"]
    assert outcome["peak_date"] == "2023-10-10"
    assert outcome["trough_date"] == "2023-09-20"


@pytest.mark.asyncio
async def test_arm_fixture_pipeline_delivered() -> None:
    store = await run_full_pipeline_e2e(
        PipelineE2EParams(
            company_name="Arm Holdings",
            mock_sec_edgar=_mock_sec_edgar_arm,
            ipo_price_history=_ipo_history_positive(),
            fetch_post_ipo_filings_return=None,
            investor_brief_overrides={
                "ipo_verdict": "delivered",
                "s1_vs_reality": "- Revenue and burn aligned with S-1 versus first 10-K.\n- Price action supportive post-IPO.",
            },
        )
    )
    assert_single_agent_pipeline_json_outputs(store)
    so = store["scenario_output"]
    assert so.get("ipo_delivery_verdict") == "delivered"
    final_report = store["final_report"]
    claim_checks = final_report.get("claim_checks") or []
    assert isinstance(claim_checks, list)
    status_by_claim_id = {c.get("claim_id"): c.get("status") for c in claim_checks if isinstance(c, dict)}
    assert status_by_claim_id.get("s1_revenue_growth") == "supported"
    assert status_by_claim_id.get("s1_burn_rate") == "supported"


@pytest.mark.asyncio
async def test_cart_fixture_pipeline_underdelivered() -> None:
    store = await run_full_pipeline_e2e(
        PipelineE2EParams(
            company_name="Maplebear Inc.",
            mock_sec_edgar=_mock_sec_edgar_cart,
            ipo_price_history=_ipo_history_cart(),
            fetch_post_ipo_filings_return=None,
            investor_brief_overrides={
                "ipo_verdict": "underdelivered",
                "s1_vs_reality": "- Revenue materially below S-1 framing versus 10-K actuals.\n- Weak post-IPO performance.",
            },
        )
    )
    assert_single_agent_pipeline_json_outputs(store)
    so = store["scenario_output"]
    assert so.get("ipo_delivery_verdict") == "underdelivered"
    final_report = store["final_report"]
    claim_checks = final_report.get("claim_checks") or []
    assert isinstance(claim_checks, list)
    status_by_claim_id = {c.get("claim_id"): c.get("status") for c in claim_checks if isinstance(c, dict)}
    assert status_by_claim_id.get("s1_revenue_growth") == "missed"


@pytest.mark.asyncio
async def test_pipeline_persists_narrative_when_llm_enabled() -> None:
    class FakeTextBlock:
        type = "text"
        text = (
            '{"headline":"Arm held up post-IPO.",'
            '"pre_ipo_story":["Strong demand into IPO."],'
            '"post_ipo_grounding":["Shares traded above IPO price."],'
            '"key_differences":["Delivery was steadier than feared."],'
            '"watch_items":["Licensing growth."],'
            '"sources_cited":["SEC EDGAR","Reuters"]}'
        )

    class FakeMessages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(content=[FakeTextBlock()])

    class FakeAnthropic:
        def __init__(self, api_key: str) -> None:
            self.messages = FakeMessages()

    with (
        patch("backend.agents.narrative_synthesiser.settings.llm_api_key", "test-key"),
        patch("backend.agents.narrative_synthesiser.settings.llm_model", "claude-test"),
        patch("backend.agents.narrative_synthesiser.anthropic.Anthropic", FakeAnthropic),
    ):
        store = await run_full_pipeline_e2e(
            PipelineE2EParams(
                company_name="Arm Holdings",
                mock_sec_edgar=_mock_sec_edgar_arm,
                ipo_price_history=_ipo_history_positive(),
            )
        )

    final_report = store["final_report"]
    assert isinstance(final_report, dict)
    assert final_report.get("narrative") is not None
    narrative = final_report["narrative"]
    assert narrative["headline"] == "Arm held up post-IPO."
    assert narrative["sources_cited"] == ["SEC EDGAR", "Reuters"]
