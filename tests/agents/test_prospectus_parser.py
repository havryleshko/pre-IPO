from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.prospectus_parser import ProspectusParser, ProspectusParserInput


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


def test_no_filing_flags_section(parser: ProspectusParser) -> None:
    harvester = {"sec_filings": [], "yahoo_finance_data": {}, "crunchbase_data": {}}
    out = parser._parse_harvester_output("SpaceX", harvester)
    assert any(f.section == "S-1 filing" for f in out.flagged_sections)
    assert out.data_confidence == "low"


def test_empty_harvester_flags_s1(parser: ProspectusParser) -> None:
    out = parser._parse_harvester_output("SpaceX", {})
    assert any(f.section == "S-1 filing" for f in out.flagged_sections)


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
