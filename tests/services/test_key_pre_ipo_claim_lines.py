from __future__ import annotations

from backend.agents.prospectus_parser import (
    S1_DISCLOSURE_CHECKLIST_CUSTOMER_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_MARKET_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_PROFIT_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_PROJECTION_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_REVENUE_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_RISK_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_SPARSE_CLAIM_ID,
)
from backend.models.single_agent_result import ClaimCheck
from backend.services.key_pre_ipo_claim_lines import build_key_pre_ipo_claim_lines


def _chk(claim_id: str, status: str, quotes: list[str] | None = None) -> ClaimCheck:
    return ClaimCheck(
        claim_id=claim_id,
        status=status,
        evidence_quotes=quotes or [],
        rationale=None,
        confidence="medium",
    )


def test_management_tone_spac_wins_over_revenue() -> None:
    checks = [
        _chk(S1_DISCLOSURE_CHECKLIST_REVENUE_CLAIM_ID, "supported", ["Revenue grew fast."]),
        _chk(S1_DISCLOSURE_CHECKLIST_PROFIT_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_CUSTOMER_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_MARKET_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_RISK_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_PROJECTION_CLAIM_ID, "supported", ["SPAC merger presentation."]),
        _chk(S1_DISCLOSURE_CHECKLIST_SPARSE_CLAIM_ID, "missed", []),
    ]
    lines, excerpts = build_key_pre_ipo_claim_lines({}, checks, [])
    assert lines[0] == "Management tone: SPAC-style projections"


def test_management_tone_vague_when_no_filing_and_placeholder_bm() -> None:
    checks = [
        _chk(S1_DISCLOSURE_CHECKLIST_REVENUE_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_PROFIT_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_CUSTOMER_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_MARKET_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_RISK_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_PROJECTION_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_SPARSE_CLAIM_ID, "supported", []),
    ]
    parser_output = {"business_model": "Business model summary not clearly stated in available filing text."}
    lines, _ = build_key_pre_ipo_claim_lines(parser_output, checks, ["Fallback from derived."])
    assert lines[0] == "Management tone: vague"
    assert any("Fallback from derived" in x for x in lines)


def test_excerpt_ordering_and_dedupe() -> None:
    checks = [
        _chk(S1_DISCLOSURE_CHECKLIST_REVENUE_CLAIM_ID, "supported", ["Same revenue story about revenue."]),
        _chk(S1_DISCLOSURE_CHECKLIST_PROFIT_CLAIM_ID, "supported", ["Path to profitability by 2026."]),
        _chk(S1_DISCLOSURE_CHECKLIST_CUSTOMER_CLAIM_ID, "supported", ["Retention 120% for enterprise cohorts."]),
        _chk(S1_DISCLOSURE_CHECKLIST_MARKET_CLAIM_ID, "supported", ["TAM of $50B CAGR 12%."]),
        _chk(S1_DISCLOSURE_CHECKLIST_RISK_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_PROJECTION_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_SPARSE_CLAIM_ID, "missed", []),
    ]
    parser_output = {
        "business_model": "We operate a vertical SaaS platform.",
        "financials": {"revenue_evidence": {"quote": "Total revenue reached $100 million."}},
    }
    lines, excerpts = build_key_pre_ipo_claim_lines(parser_output, checks, [])
    assert lines[0] == "Management tone: conservative"
    joined = "\n".join(lines)
    assert "Total revenue reached" in joined
    assert "Path to profitability" in joined
    assert excerpts[0].startswith("Total revenue")


def test_roadshow_when_filing_thin() -> None:
    checks = [
        _chk(S1_DISCLOSURE_CHECKLIST_REVENUE_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_PROFIT_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_CUSTOMER_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_MARKET_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_RISK_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_PROJECTION_CLAIM_ID, "missed", []),
        _chk(S1_DISCLOSURE_CHECKLIST_SPARSE_CLAIM_ID, "supported", ["Lock-up period is 180 days."]),
    ]
    parser_output = {
        "business_model": "Real model sentence here.",
        "demand_signals": {"roadshow_sentiment": "Strong institutional interest at roadshow.", "institutional_interest": "high"},
    }
    lines, _ = build_key_pre_ipo_claim_lines(parser_output, checks, [])
    assert any("roadshow" in x.lower() for x in lines[1:])
