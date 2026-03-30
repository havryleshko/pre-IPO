from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.prospectus_parser import ProspectusParser, ProspectusParserInput
from backend.models.parser_output import ActualResult, S1Projection


SAMPLE_S1_WITH_FINANCIALS = """
Our business model focuses on space transportation. We provide launch services.
Total revenue for the year was $1,500 million. Year-over-year growth of 45%.
Cash used in operating activities was $50 million per month. Cash runway 18 months.
We intend to use the net proceeds from this offering for capital expenditures.
Elon Musk, our Chief Executive Officer, has led the company since 2002.
The 180 days lock-up period applies to insiders.
Total shares offered 100,000,000. Shares by existing stockholders 30,000,000.
Public float 70,000,000. The underwriters have an over-allotment option.
Strong institutional interest. The roadshow was oversubscribed.
"""

SAMPLE_S1_REDACTED = """
Our business model. [REDACTED] [REDACTED] [REDACTED].
Revenue and financial metrics [REDACTED]. Use of proceeds [REDACTED].
"""

SAMPLE_S1_OFFERING_STRUCTURE_SECTIONED = """
PROSPECTUS
Total shares offered 100,000,000.
Public float 50,000,000.

UNDERWRITING
The 180 days lock-up period applies to insiders.
Total shares offered 90,000,000.
Shares by existing stockholders 30,000,000.
Public float 70,000,000.
The underwriters have an over-allotment option.

We intend to use the net proceeds from this offering for capital expenditures.
"""

SAMPLE_S1_FINANCIALS_SECTIONED = """
PROSPECTUS
Total revenue $999 million.

FINANCIAL STATEMENTS
Total revenue for the year was $2,500 million. Year-over-year growth of 20%.
Cash used in operating activities was $60 million per month. Cash runway 15 months.

UNDERWRITING
The 180 days lock-up period applies to insiders.
Total shares offered 100,000,000. Shares by existing stockholders 30,000,000.
Public float 70,000,000. The underwriters have an over-allotment option.
"""

SAMPLE_S1_USE_OF_PROCEEDS_SECTIONED = """
PROSPECTUS
We intend to allocate proceeds to growth initiatives.

USE OF PROCEEDS
We intend to use the net proceeds from this offering for capital expenditures and working capital.
"""

SAMPLE_S1_RISK_FACTORS_SECTIONED = """
PROSPECTUS
Table of Contents. Investing in our Class A common stock involves risks.

RISK FACTORS
The risks of the Company include uncertainty regarding its ability to sustain revenue growth and achieve profitability in competitive markets, which could adversely affect our results.
Another risk is that we may incur additional costs due to evolving regulatory requirements and changes in the market for our products.
"""

ARM_LIKE_10K_TEXT = """
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
Cash used in operating activities was $450 million for the year ended December 31, 2024.
"""


@pytest.fixture
def parser() -> ProspectusParser:
    return ProspectusParser()


def test_extracts_revenue_from_s1(parser: ProspectusParser) -> None:
    harvester = {
        "sec_filings": [{"text": SAMPLE_S1_WITH_FINANCIALS}],
        "yahoo_finance_data": {"comparable_companies": ["A"], "sector_multiples": {"trailing_pe_median": 25.0}},
        "crunchbase_data": {"investors": ["Sequoia"], "funding_rounds": []},
    }
    out = parser._parse_harvester_output("SpaceX", harvester)
    assert out.financials.revenue == 1_500_000_000
    assert out.financials.burn_rate_monthly == 50_000_000
    assert out.financials.cash_runway_months == 18
    assert out.financials.revenue_growth_yoy == 45.0


def test_extracts_lockup_and_float(parser: ProspectusParser) -> None:
    harvester = {
        "sec_filings": [{"text": SAMPLE_S1_WITH_FINANCIALS}],
        "yahoo_finance_data": {},
        "crunchbase_data": {},
    }
    out = parser._parse_harvester_output("SpaceX", harvester)
    assert out.lockup_period_days == 180
    assert out.float_details.total_shares_offered == 100_000_000
    assert out.float_details.insider_shares == 30_000_000
    assert out.float_details.public_float == 70_000_000
    assert out.float_details.greenshoe_option is True


def test_extracts_offering_structure_from_sections(parser: ProspectusParser) -> None:
    harvester = {
        "sec_filings": [{"text": SAMPLE_S1_OFFERING_STRUCTURE_SECTIONED}],
        "yahoo_finance_data": {},
        "crunchbase_data": {},
    }
    out = parser._parse_harvester_output("SpaceX", harvester)

    assert out.lockup_period_days == 180
    assert out.float_details.total_shares_offered == 100_000_000
    assert out.float_details.insider_shares == 30_000_000
    assert out.float_details.public_float == 70_000_000
    assert out.float_details.greenshoe_option is True


def test_extracts_financials_from_financial_statements_section(parser: ProspectusParser) -> None:
    harvester = {
        "sec_filings": [{"text": SAMPLE_S1_FINANCIALS_SECTIONED}],
        "yahoo_finance_data": {},
        "crunchbase_data": {},
    }
    out = parser._parse_harvester_output("SpaceX", harvester)

    assert out.financials.revenue == 2_500_000_000
    assert out.financials.revenue_growth_yoy == 20.0
    assert out.financials.burn_rate_monthly == 60_000_000
    assert out.financials.cash_runway_months == 15


def test_extracts_key_people(parser: ProspectusParser) -> None:
    harvester = {
        "sec_filings": [{"text": SAMPLE_S1_WITH_FINANCIALS}],
        "yahoo_finance_data": {},
        "crunchbase_data": {},
    }
    out = parser._parse_harvester_output("SpaceX", harvester)
    assert len(out.key_people) >= 1
    ceo = next((p for p in out.key_people if p.role == "CEO"), None)
    assert ceo is not None
    assert "Elon" in ceo.name or "Musk" in ceo.name


def test_extracts_use_of_proceeds(parser: ProspectusParser) -> None:
    harvester = {
        "sec_filings": [{"text": SAMPLE_S1_WITH_FINANCIALS}],
        "yahoo_finance_data": {},
        "crunchbase_data": {},
    }
    out = parser._parse_harvester_output("SpaceX", harvester)
    assert "proceeds" in out.use_of_proceeds.lower() or "capital" in out.use_of_proceeds.lower()


def test_extracts_use_of_proceeds_from_sections(parser: ProspectusParser) -> None:
    harvester = {
        "sec_filings": [{"text": SAMPLE_S1_USE_OF_PROCEEDS_SECTIONED}],
        "yahoo_finance_data": {},
        "crunchbase_data": {},
    }
    out = parser._parse_harvester_output("SpaceX", harvester)
    assert "capital expenditures" in out.use_of_proceeds.lower()
    assert "growth initiatives" not in out.use_of_proceeds.lower()


def test_extracts_structured_risk_factors_and_filters_toc_noise(parser: ProspectusParser) -> None:
    harvester = {
        "sec_filings": [{"text": SAMPLE_S1_RISK_FACTORS_SECTIONED}],
        "yahoo_finance_data": {},
        "crunchbase_data": {},
    }
    out = parser._parse_harvester_output("SpaceX", harvester)

    assert not any("Table of Contents" in r for r in out.risk_factors)
    assert any("sustain revenue growth" in r for r in out.risk_factors)

    assert len(out.risk_factors_evidence) >= 1
    assert any(
        "sustain revenue growth" in e.risk_factor for e in out.risk_factors_evidence
    )
    assert all(
        e.source_reference == "SEC EDGAR S-1 — Risk Factors section"
        for e in out.risk_factors_evidence
    )


def test_no_filing_flags_section(parser: ProspectusParser) -> None:
    harvester = {"sec_filings": [], "yahoo_finance_data": {}, "crunchbase_data": {}}
    out = parser._parse_harvester_output("SpaceX", harvester)
    assert any(f.section == "S-1 filing" for f in out.flagged_sections)
    assert out.data_confidence == "low"


def test_empty_harvester_flags_s1(parser: ProspectusParser) -> None:
    out = parser._parse_harvester_output("SpaceX", {})
    assert any(f.section == "S-1 filing" for f in out.flagged_sections)


def test_rejects_implausible_money_values(parser: ProspectusParser) -> None:
    harvester = {
        "sec_filings": [
            {
                "text": "Revenue was 456. Cash used in operating activities 333. "
                "Total revenue $1,500 million. Burn rate $50 million per month.",
            }
        ],
        "yahoo_finance_data": {},
        "crunchbase_data": {},
    }
    out = parser._parse_harvester_output("TestCo", harvester)
    assert out.financials.revenue == 1_500_000_000
    assert out.financials.burn_rate_monthly == 50_000_000


def test_filters_risk_factor_toc_noise(parser: ProspectusParser) -> None:
    harvester = {
        "sec_filings": [
            {
                "text": "Table of Contents. Investing in our Class A common stock involves risks. "
                "KLEIN & COMPANY MACQUARIE CAPITAL. "
                "We face significant risks related to our ability to sustain revenue growth and achieve profitability "
                "in competitive markets with evolving regulatory requirements.",
            }
        ],
        "yahoo_finance_data": {},
        "crunchbase_data": {},
    }
    out = parser._parse_harvester_output("TestCo", harvester)
    assert not any("involves risks" in r for r in out.risk_factors)
    assert not any("KLEIN" in r for r in out.risk_factors)
    assert any("sustain revenue growth" in r for r in out.risk_factors)


def test_missing_financials_flags_section(parser: ProspectusParser) -> None:
    harvester = {
        "sec_filings": [{"text": "Our business. No revenue or burn rate mentioned here."}],
        "yahoo_finance_data": {},
        "crunchbase_data": {},
    }
    out = parser._parse_harvester_output("SpaceX", harvester)
    assert out.financials.revenue is None
    assert out.financials.burn_rate_monthly is None
    assert any(f.section == "Financials" for f in out.flagged_sections)


def test_redacted_filing_low_confidence(parser: ProspectusParser) -> None:
    harvester = {
        "sec_filings": [{"text": SAMPLE_S1_REDACTED}],
        "yahoo_finance_data": {},
        "crunchbase_data": {},
    }
    out = parser._parse_harvester_output("SpaceX", harvester)
    assert out.financials.revenue is None
    assert out.financials.burn_rate_monthly is None
    assert out.data_confidence == "low"


def test_extracts_funding_history_from_crunchbase(parser: ProspectusParser) -> None:
    harvester = {
        "sec_filings": [{"text": "Business model."}],
        "yahoo_finance_data": {},
        "crunchbase_data": {
            "funding_rounds": [
                {"round": "Series F", "amount": 500_000_000, "date": "2024-01-15", "investors": ["VC1"], "valuation": 50_000_000_000},
            ]
        },
    }
    out = parser._parse_harvester_output("SpaceX", harvester)
    assert len(out.funding_history) == 1
    assert out.funding_history[0].round == "Series F"
    assert out.funding_history[0].amount == 500_000_000
    assert out.funding_history[0].valuation == 50_000_000_000


@pytest.mark.asyncio
async def test_run_persists_output(parser: ProspectusParser) -> None:
    analysis = {
        "company_name": "SpaceX",
        "harvester_output": {
            "sec_filings": [{"text": SAMPLE_S1_WITH_FINANCIALS}],
            "yahoo_finance_data": {},
            "crunchbase_data": {},
        },
    }
    with (
        patch("backend.agents.prospectus_parser.get_analysis_by_id", new_callable=AsyncMock, return_value=analysis),
        patch("backend.agents.prospectus_parser.save_parser_output", new_callable=AsyncMock) as save_mock,
        patch("backend.agents.prospectus_parser.log_agent_run_start", new_callable=AsyncMock, return_value={"id": "run-1"}),
        patch("backend.agents.prospectus_parser.log_agent_run_completed", new_callable=AsyncMock),
    ):
        result = await parser.run(ProspectusParserInput(analysis_id="test-id"))
    assert result.analysis_id == "test-id"
    saved = save_mock.call_args.kwargs["output"]
    assert saved["company_name"] == "SpaceX"
    assert saved["financials"]["revenue"] == 1_500_000_000


def test_parse_10k_actuals_returns_revenue_burn_and_capped_risks(parser: ProspectusParser) -> None:
    actuals = parser.parse_10k_actuals(ARM_LIKE_10K_TEXT)
    by_metric = {a.metric: a for a in actuals}
    assert by_metric["revenue"].actual_value == 2_800_000_000
    assert by_metric["revenue"].source_filing == "10-K"
    assert by_metric["burn_rate"].actual_value is not None
    assert by_metric["burn_rate"].metric == "burn_rate"
    risk_rows = [a for a in actuals if a.metric.startswith("risk_factor_")]
    assert len(risk_rows) <= 5


def test_compare_s1_to_10k_missed(parser: ProspectusParser) -> None:
    s1 = [S1Projection(metric="revenue", s1_value=3_000_000_000, s1_context="S-1")]
    act = [ActualResult(metric="revenue", actual_value=2_400_000_000, source_filing="10-K", source_section="x")]
    evidence = parser.compare_s1_to_10k(s1, act)
    assert len(evidence) == 1
    assert evidence[0].verdict == "missed"


def test_compare_s1_to_10k_met(parser: ProspectusParser) -> None:
    s1 = [S1Projection(metric="revenue", s1_value=100.0, s1_context="S-1")]
    act = [ActualResult(metric="revenue", actual_value=100.0, source_filing="10-K", source_section="x")]
    evidence = parser.compare_s1_to_10k(s1, act)
    assert len(evidence) == 1
    assert evidence[0].verdict == "met"


def test_compare_s1_to_10k_exceeded(parser: ProspectusParser) -> None:
    s1 = [S1Projection(metric="revenue", s1_value=1_000_000.0, s1_context="S-1")]
    act = [ActualResult(metric="revenue", actual_value=2_000_000.0, source_filing="10-K", source_section="x")]
    evidence = parser.compare_s1_to_10k(s1, act)
    assert len(evidence) == 1
    assert evidence[0].verdict == "exceeded"


def test_parse_harvester_with_10k_sets_has_post_ipo_10k_and_actuals(parser: ProspectusParser) -> None:
    harvester = {
        "sec_filings": [
            {"filing_type": "S-1", "text": SAMPLE_S1_WITH_FINANCIALS},
            {"filing_type": "10-K", "text": ARM_LIKE_10K_TEXT},
        ],
        "yahoo_finance_data": {"comparable_companies": ["A"], "sector_multiples": {"trailing_pe_median": 25.0}},
        "crunchbase_data": {},
    }
    out = parser._parse_harvester_output("ARM", harvester)
    assert out.has_post_ipo_10k is True
    metrics = {a.metric: a for a in out.actuals}
    assert "revenue" in metrics
    assert "burn_rate" in metrics
    assert out.financials.revenue == 1_500_000_000
