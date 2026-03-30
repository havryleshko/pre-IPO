from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def client() -> TestClient:
    with (
        patch("backend.main.get_pool", new_callable=AsyncMock),
        patch("backend.main.close_pool", new_callable=AsyncMock),
    ):
        app = create_app()
        with TestClient(app) as c:
            yield c


def test_create_analysis_returns_analysis_id(client: TestClient) -> None:
    analysis_id = str(uuid4())
    record = {
        "id": analysis_id,
        "company_name": "TestCo",
        "status": "pending",
        "complexity_tier": "standard",
        "created_at": datetime.now(timezone.utc),
    }
    with (
        patch(
            "backend.api.routes_analysis.create_analysis",
            new_callable=AsyncMock,
            return_value=record,
        ),
        patch("backend.api.routes_analysis._schedule_pipeline") as schedule_pipeline,
    ):
        resp = client.post("/analyses", json={"company_name": "TestCo"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["company_name"] == "TestCo"
    assert data["analysis_id"] == analysis_id
    assert data["status"] == "pending"
    assert data["complexity_tier"] == "standard"
    schedule_pipeline.assert_called_once_with(analysis_id)


def test_create_analysis_returns_500_when_create_fails(client: TestClient) -> None:
    with (
        patch(
            "backend.api.routes_analysis.create_analysis",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("backend.api.routes_analysis._schedule_pipeline") as schedule_pipeline,
    ):
        resp = client.post("/analyses", json={"company_name": "TestCo"})
    assert resp.status_code == 500
    schedule_pipeline.assert_not_called()


def test_create_analysis_returns_200_when_pipeline_schedule_fails(client: TestClient) -> None:
    analysis_id = str(uuid4())
    record = {
        "id": analysis_id,
        "company_name": "TestCo",
        "status": "pending",
        "complexity_tier": "standard",
        "created_at": datetime.now(timezone.utc),
    }
    with (
        patch(
            "backend.api.routes_analysis.create_analysis",
            new_callable=AsyncMock,
            return_value=record,
        ),
        patch(
            "backend.api.routes_analysis._schedule_pipeline",
            side_effect=RuntimeError("boom"),
        ),
    ):
        resp = client.post("/analyses", json={"company_name": "TestCo"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["analysis_id"] == analysis_id


def test_get_analysis_returns_200_with_outputs(client: TestClient) -> None:
    analysis_id = str(uuid4())
    record = {
        "id": analysis_id,
        "company_name": "TestCo",
        "status": "completed",
        "complexity_tier": "standard",
        "last_completed_agent": "investor_brief_synthesizer",
        "created_at": datetime.now(timezone.utc),
        "harvester_output": None,
        "parser_output": None,
        "scenario_output": None,
        "investor_brief": None,
        "recommendation_output": None,
    }
    with patch(
        "backend.api.routes_analysis.get_analysis_by_id",
        new_callable=AsyncMock,
        return_value=record,
    ):
        resp = client.get(f"/analyses/{analysis_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["analysis_id"] == analysis_id
    assert data["company_name"] == "TestCo"
    assert data["status"] == "completed"
    assert data["last_completed_agent"] == "investor_brief_synthesizer"


def test_get_analysis_returns_404_when_not_found(client: TestClient) -> None:
    with patch(
        "backend.api.routes_analysis.get_analysis_by_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = client.get(f"/analyses/{uuid4()}")
    assert resp.status_code == 404
