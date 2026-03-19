from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.export.pdf_full_report import generate_full_report_pdf
from backend.export.pdf_summary import generate_summary_pdf
from backend.main import create_app


def _minimal_record() -> dict:
    return {
        "company_name": "TestCo",
        "status": "completed",
        "export_locked": False,
        "judge_output": {"validation_passed": True},
        "created_at": datetime.now(timezone.utc),
        "scenario_output": {
            "scenarios": {
                "pessimistic": {
                    "probability": 25,
                    "price_targets": {"30_days": 10.0, "90_days": 12.0, "1_year": 14.0},
                },
                "realistic": {
                    "probability": 50,
                    "price_targets": {"30_days": 12.0, "90_days": 15.0, "1_year": 18.0},
                },
                "optimistic": {
                    "probability": 25,
                    "price_targets": {"30_days": 14.0, "90_days": 18.0, "1_year": 22.0},
                },
            },
        },
        "recommendation_output": {
            "decision": "buy",
            "decision_scope": "pre_ipo_fund",
            "decision_rationale": "Buy because entry conditions look met.",
            "entry_triggers": ["Entry thesis", "Offering structure"],
            "watch_triggers": ["Verify flagged sections"],
            "kill_criteria": ["Kill: recommendation is avoid"],
            "decision_evidence": ["parser:data_confidence=high", "harvester:sec_filings_count=1"],
            "funds_to_consider": ["Example Pre-IPO Fund"],
            "retail_summary": {
                "verdict_line": "TestCo likely has upside over 12+ months based on current filing and market evidence.",
                "what_i_see_now": [
                    "Decision: BUY (pre-IPO fund)",
                    "Data confidence: high",
                    "Base scenario probability: 50.0% (upside 25.0%, downside 25.0%)",
                ],
                "why_that_matters": [
                    "Scenarios define how much upside and downside risk is currently priced into the stance.",
                    "This view is built to monitor evidence quality as the offering information updates.",
                ],
                "the_good": [
                    "Revenue baseline is available at $100.0M.",
                    "Scenario structure is available and supports disciplined monitoring.",
                ],
                "the_risk": [
                    "Monthly burn is around $5.0M, which can pressure execution.",
                    "Kill: tradability evidence fails validation (public float/lock-up not defensible).",
                ],
                "simple_conclusion": "TestCo is a buy with staged sizing and active risk controls.",
                "key_data_points": [
                    "Pessimistic / Realistic / Optimistic probabilities: 25.0% / 50.0% / 25.0%",
                    "Data confidence: high",
                    "Revenue: $100.0M",
                    "Burn rate: $5.0M per month",
                ],
                "action_ideas": {
                    "conservative": "Take no position yet and monitor until verified filing metrics are available.",
                    "tactical": "Use staged entry once entry triggers are confirmed.",
                    "risk_control": "Kill criteria: exit or avoid if downside risk becomes dominant.",
                },
                "is_preliminary": False,
            },
            "recommendations": {
                "pessimistic": {
                    "recommended_positioning": "capital preservation",
                    "risk_warning": "Downside risk elevated.",
                },
                "realistic": {
                    "recommended_positioning": "balanced",
                    "risk_warning": "Base case may deviate.",
                },
                "optimistic": {
                    "recommended_positioning": "growth-forward",
                    "risk_warning": "Upside can unwind.",
                },
            },
            "plain_english_summary": "TestCo shows balanced exposure across scenarios.",
        },
        "harvester_output": {
            "sources_active": ["sec_edgar", "news_api"],
            "harvested_at": datetime.now(timezone.utc),
        },
    }


def _is_valid_pdf(data: bytes) -> bool:
    return data.startswith(b"%PDF") and b"%%EOF" in data[-1024:]


import base64
import re
import zlib


_STREAM_RE = re.compile(rb"stream\s*(.*?)\s*endstream", re.DOTALL)


def _pdf_contains(pdf_bytes: bytes, text: str) -> None:
    needle = text.encode("utf-8")
    for match in _STREAM_RE.finditer(pdf_bytes):
        stream_data = match.group(1).strip()
        for ascii85_first in (True, False):
            try:
                if ascii85_first:
                    for adobe_flag in (False, True):
                        try:
                            decoded = base64.a85decode(stream_data, adobe=adobe_flag)
                            try:
                                decompressed = zlib.decompress(decoded)
                                if needle in decompressed:
                                    return
                            except zlib.error:
                                if needle in decoded:
                                    return
                        except Exception:
                            continue
                else:
                    try:
                        decompressed = zlib.decompress(stream_data)
                        if needle in decompressed:
                            return
                    except zlib.error:
                        if needle in stream_data:
                            return
            except Exception:
                continue
    assert False, f"Expected to find {text!r} in decoded PDF streams"


@pytest.mark.asyncio
async def test_generate_summary_pdf_returns_valid_pdf() -> None:
    record = _minimal_record()
    pdf_bytes = await generate_summary_pdf(record)
    assert len(pdf_bytes) > 100
    assert _is_valid_pdf(pdf_bytes)
    _pdf_contains(pdf_bytes, "Simple Investor View")
    _pdf_contains(pdf_bytes, "TestCo likely has upside over 12+ months")
    _pdf_contains(pdf_bytes, "What I See Now")
    _pdf_contains(pdf_bytes, "The Good")
    _pdf_contains(pdf_bytes, "The Risk")
    _pdf_contains(pdf_bytes, "Simple Conclusion")
    _pdf_contains(pdf_bytes, "Key Data Points Used")
    _pdf_contains(pdf_bytes, "Short Action Ideas")
    _pdf_contains(pdf_bytes, "Conservative:")
    _pdf_contains(pdf_bytes, "Tactical:")
    _pdf_contains(pdf_bytes, "Risk control:")


@pytest.mark.asyncio
async def test_generate_full_report_pdf_returns_valid_pdf() -> None:
    record = _minimal_record()
    pdf_bytes = await generate_full_report_pdf(record)
    assert len(pdf_bytes) > 500
    assert _is_valid_pdf(pdf_bytes)
    _pdf_contains(pdf_bytes, "Simple Investor View")
    _pdf_contains(pdf_bytes, "TestCo likely has upside over 12+ months")
    _pdf_contains(pdf_bytes, "Simple Conclusion")


@pytest.mark.asyncio
async def test_generate_pdfs_allow_xml_metacharacters() -> None:
    record = _minimal_record()
    record["company_name"] = "AT&T <IPO>"
    record["recommendation_output"]["decision_rationale"] = "Buy <now> & hold if demand > supply."
    record["recommendation_output"]["plain_english_summary"] = "AT&T <IPO> & peers look constructive."
    record["recommendation_output"]["funds_to_consider"] = ["Growth & Income Fund <A>"]
    record["recommendation_output"]["retail_summary"]["verdict_line"] = "AT&T <IPO> & peers look constructive <now>."
    record["recommendation_output"]["retail_summary"]["action_ideas"]["conservative"] = "AT&T <IPO> & peers: wait <now>."
    record["recommendation_output"]["retail_summary"]["action_ideas"]["risk_control"] = "Risk: exit if demand <now> drops & breaks."
    summary_bytes = await generate_summary_pdf(record)
    full_bytes = await generate_full_report_pdf(record)
    assert _is_valid_pdf(summary_bytes)
    assert _is_valid_pdf(full_bytes)


@pytest.fixture
def client() -> TestClient:
    with (
        patch("backend.main.get_pool", new_callable=AsyncMock),
        patch("backend.main.close_pool", new_callable=AsyncMock),
    ):
        app = create_app()
        with TestClient(app) as c:
            yield c


def test_export_summary_endpoint_returns_pdf(client: TestClient) -> None:
    analysis_id = str(uuid4())
    record = _minimal_record()
    record["export_locked"] = False
    with patch(
        "backend.api.routes_export.get_analysis_by_id",
        new_callable=AsyncMock,
        return_value=record,
    ):
        resp = client.get(f"/analyses/{analysis_id}/export/summary")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert _is_valid_pdf(resp.content)
    assert "attachment" in resp.headers.get("content-disposition", "")
    _pdf_contains(resp.content, "Simple Investor View")
    _pdf_contains(resp.content, "Short Action Ideas")
    _pdf_contains(resp.content, "Conservative:")


def test_export_full_endpoint_returns_pdf(client: TestClient) -> None:
    analysis_id = str(uuid4())
    record = _minimal_record()
    record["export_locked"] = False
    with patch(
        "backend.api.routes_export.get_analysis_by_id",
        new_callable=AsyncMock,
        return_value=record,
    ):
        resp = client.get(f"/analyses/{analysis_id}/export/full")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert _is_valid_pdf(resp.content)
    _pdf_contains(resp.content, "Simple Investor View")
    _pdf_contains(resp.content, "Simple Conclusion")


def test_export_locked_returns_403(client: TestClient) -> None:
    analysis_id = str(uuid4())
    record = _minimal_record()
    record["export_locked"] = True
    with patch(
        "backend.api.routes_export.get_analysis_by_id",
        new_callable=AsyncMock,
        return_value=record,
    ):
        resp = client.get(f"/analyses/{analysis_id}/export/summary")
    assert resp.status_code == 403


def test_export_summary_requires_completed_analysis(client: TestClient) -> None:
    analysis_id = str(uuid4())
    record = _minimal_record()
    record["status"] = "pending"
    with patch(
        "backend.api.routes_export.get_analysis_by_id",
        new_callable=AsyncMock,
        return_value=record,
    ):
        resp = client.get(f"/analyses/{analysis_id}/export/summary")
    assert resp.status_code == 403


def test_export_summary_requires_judge_validation(client: TestClient) -> None:
    analysis_id = str(uuid4())
    record = _minimal_record()
    record["judge_output"] = {"validation_passed": False}
    with patch(
        "backend.api.routes_export.get_analysis_by_id",
        new_callable=AsyncMock,
        return_value=record,
    ):
        resp = client.get(f"/analyses/{analysis_id}/export/summary")
    assert resp.status_code == 403
