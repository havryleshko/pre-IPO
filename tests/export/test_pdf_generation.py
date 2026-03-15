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


@pytest.mark.asyncio
async def test_generate_summary_pdf_returns_valid_pdf() -> None:
    record = _minimal_record()
    pdf_bytes = await generate_summary_pdf(record)
    assert len(pdf_bytes) > 100
    assert _is_valid_pdf(pdf_bytes)


@pytest.mark.asyncio
async def test_generate_full_report_pdf_returns_valid_pdf() -> None:
    record = _minimal_record()
    pdf_bytes = await generate_full_report_pdf(record)
    assert len(pdf_bytes) > 500
    assert _is_valid_pdf(pdf_bytes)


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
