from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tui.export import export_all
from tui.render import render_result_markdown, render_result_plain
from tui.types import (
    ClaimCheck,
    CompanyProfile,
    FilingFact,
    NarrativeReport,
    NewsDerivedClaim,
    NewsFilingDiscrepancy,
    OutcomeMetrics,
    PatternFlag,
    PatternClassification,
    PreIpoThesis,
    PredictionClaim,
    RealizedOutcome,
    ReferenceTableRow,
    SingleAgentResult,
)


def _sample_narrative() -> NarrativeReport:
    return NarrativeReport(
        headline="TestCo delivered modest gains but missed growth targets.",
        pre_ipo_story=["S-1 promised 40% revenue growth.", "Institutional demand was strong."],
        post_ipo_grounding=["Revenue grew only 18% in first year.", "Stock dropped 30% at lock-up cliff."],
        key_differences=["Growth miss of 22 percentage points.", "Insider selling higher than disclosed."],
        watch_items=["Next earnings release.", "Secondary offering risk."],
        sources_cited=["SEC EDGAR S-1", "Reuters post-IPO coverage"],
    )


def _sample_result() -> SingleAgentResult:
    return SingleAgentResult(
        company_name="TestCo",
        generated_at=datetime.now(timezone.utc),
        prediction_claims=[
            PredictionClaim(
                claim_id="c1",
                claim_type="growth",
                prediction_text="Revenue will grow fast.",
                source="internet",
                source_url=None,
                published_at=None,
            )
        ],
        filing_facts=[],
        outcome_metrics=OutcomeMetrics(
            ipo_price=10.0,
            current_price=12.5,
            performance_since_ipo_pct=25.0,
        ),
        company_profile=CompanyProfile(
            issuer_name="TestCo",
            ticker="TCO",
            company_ticker="TestCo (TCO)",
            industry_region="Software / US",
            ipo_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
            listing_type="primary",
        ),
        pre_ipo_thesis=PreIpoThesis(key_pre_ipo_claims=["Subscription software growth story."]),
        realized_outcome=RealizedOutcome(
            long_term_outcome="IPO $10; current $12.50; post-IPO performance positive.",
            forecast_error="Post-IPO results broadly aligned with the main S-1 framing.",
        ),
        pattern_classification=PatternClassification(
            primary_pattern_id=2,
            primary_pattern_label="Pattern 2: Steady compounders with conservative narratives",
            analog_companies=["Atlassian (TEAM)", "Salesforce (CRM)"],
            source="reference_exact",
        ),
        reference_table_row=ReferenceTableRow(
            company_ticker="TestCo (TCO)",
            industry_region="Software / US",
            ipo_date="2024-01-01",
            key_pre_ipo_claims="Subscription software growth story.",
            long_term_outcome="IPO $10; current $12.50; post-IPO performance positive.",
            forecast_error="Post-IPO results broadly aligned with the main S-1 framing.",
            predicted_pattern="Pattern 2: Steady compounders with conservative narratives",
        ),
        claim_checks=[
            ClaimCheck(
                claim_id="c1",
                status="supported",
                evidence_quotes=["S-1 projection: X", "10-K actual: Y"],
                confidence="high",
            )
        ],
        patterns=[PatternFlag(signal="Lock-up cliff stress", was_visible_at_ipo=True, outcome="Down 20% after lockup")],
        narrative=_sample_narrative(),
    )


def test_render_plain_contains_sections() -> None:
    s = render_result_plain(_sample_result())
    assert "TestCo" in s
    assert "Reference table row" in s
    assert "Company (Ticker)" in s
    assert "Industry / Region" in s
    assert "Outcome" in s
    assert "IPO price" in s
    assert "Pre-IPO story" in s
    assert "Post-IPO grounding" in s
    assert "Key differences" in s
    assert "What to watch" in s
    assert "Sources" in s
    assert "TestCo delivered modest gains" in s


def test_render_plain_fallback_without_narrative() -> None:
    result = _sample_result()
    result.narrative = None
    s = render_result_plain(result)
    assert "S-1 claim checks" in s
    assert "Patterns" in s
    assert "Pre-IPO story" not in s
    assert s.index("S-1 claim checks") < s.index("Patterns")


def test_render_markdown_contains_headers() -> None:
    s = render_result_markdown(_sample_result())
    assert s.startswith("# TestCo")
    assert "## Reference table row" in s
    assert "## Outcome" in s
    assert "## Pre-IPO story" in s
    assert "## Post-IPO grounding" in s
    assert "## Key differences" in s
    assert "## What to watch" in s
    assert "## Sources" in s


def test_render_markdown_fallback_without_narrative() -> None:
    result = _sample_result()
    result.narrative = None
    s = render_result_markdown(result)
    assert "## S-1 claim checks" in s
    assert "## Pre-IPO story" not in s
    assert s.index("## S-1 claim checks") < s.index("## Patterns")


def test_export_all_writes_three_files(tmp_path: Path) -> None:
    out = export_all(analysis_id="aid-1", result=_sample_result(), base_dir=str(tmp_path))
    txt = out / "analysis.txt"
    md = out / "analysis.md"
    js = out / "analysis.json"
    assert txt.is_file()
    assert md.is_file()
    assert js.is_file()
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert payload["company_name"] == "TestCo"


def test_render_plain_grounded_sections_visible_with_narrative() -> None:
    result = _sample_result()
    result.narrative = _sample_narrative()
    result.patterns = [PatternFlag(signal="Burn rate spike", was_visible_at_ipo=True, outcome="Cash crunch within 12m")]
    result.filing_facts = [
        FilingFact(fact_id="ff1", metric="total_revenue_2022", value=500.0, units="$M", source="s1_f1")
    ]
    result.claim_checks = [
        ClaimCheck(claim_id="c1", status="missed", evidence_quotes=["S-1: 40%", "10-K: 18%"], confidence="high")
    ]
    s = render_result_plain(result)
    assert "Patterns" in s
    assert "Filing snapshot" in s
    assert "S-1 claim checks" in s
    assert "Pre-IPO story" in s


def test_render_markdown_grounded_sections_visible_with_narrative() -> None:
    result = _sample_result()
    result.narrative = _sample_narrative()
    result.patterns = [PatternFlag(signal="Revenue miss", was_visible_at_ipo=False, outcome="Underperformed")]
    result.filing_facts = [
        FilingFact(fact_id="ff1", metric="net_loss_2022", value=-120.0, units="$M", source="s1_f1")
    ]
    s = render_result_markdown(result)
    assert "## Patterns" in s
    assert "## Filing snapshot" in s
    assert "## Pre-IPO story" in s


def test_tui_types_parse_news_fields() -> None:
    payload = {
        "company_name": "AcmeCo",
        "generated_at": "2024-01-01T00:00:00",
        "reference_table_row": {
            "company_ticker": "AcmeCo (ACME)",
            "industry_region": "Fintech / US",
            "ipo_date": "2024-01-01",
            "key_pre_ipo_claims": "Fintech growth story.",
            "long_term_outcome": "IPO $10; current $8.",
            "forecast_error": "Growth lagged the pre-IPO framing.",
            "predicted_pattern": "Pattern 1: Hyped growth story, weak long-run performance",
        },
        "pattern_classification": {
            "primary_pattern_id": 1,
            "primary_pattern_label": "Pattern 1: Hyped growth story, weak long-run performance",
            "confidence": "medium",
            "analog_companies": ["Snap (SNAP)"],
            "source": "heuristic",
        },
        "news_derived_claims": [
            {
                "claim_id": "nc1",
                "claim_type": "valuation",
                "normalized_value": 65.0,
                "units": "$B",
                "period": None,
                "source": "news_api",
                "evidence_quote": "AcmeCo valued at $65B",
                "article_url": "https://example.com/1",
                "published_at": None,
            }
        ],
        "news_filing_discrepancies": [
            {
                "discrepancy_id": "d1",
                "news_claim_id": "nc1",
                "contradiction_type": "derived_numeric_contradiction",
                "news_evidence": "news says $65B",
                "filing_evidence": "filing implies $50B",
                "derived_value_filing": 50.0,
                "derived_value_news": 65.0,
            }
        ],
    }
    r = SingleAgentResult.model_validate(payload)
    assert len(r.news_derived_claims) == 1
    assert r.news_derived_claims[0].claim_id == "nc1"
    assert r.news_derived_claims[0].normalized_value == 65.0
    assert len(r.news_filing_discrepancies) == 1
    assert r.news_filing_discrepancies[0].discrepancy_id == "d1"
    assert r.reference_table_row is not None
    assert r.reference_table_row.company_ticker == "AcmeCo (ACME)"
    assert r.pattern_classification is not None
    assert r.pattern_classification.primary_pattern_id == 1

