import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api.websocket_progress import (
    broadcast_to_analysis,
    emit_agent_status,
)
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


def test_websocket_accepts_connection(client: TestClient) -> None:
    with client.websocket_connect("/analyses/test-id/progress") as websocket:
        websocket.send_text("ping")


@pytest.mark.asyncio
async def test_broadcast_to_analysis_sends_to_connected_socket() -> None:
    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock()
    with patch(
        "backend.api.websocket_progress._connections",
        {"analysis-1": {mock_ws}},
    ):
        await broadcast_to_analysis("analysis-1", {"type": "test", "data": "hello"})
    mock_ws.send_text.assert_called_once()
    payload = json.loads(mock_ws.send_text.call_args[0][0])
    assert payload == {"type": "test", "data": "hello"}


@pytest.mark.asyncio
async def test_emit_agent_status_broadcasts_correct_payload() -> None:
    with patch(
        "backend.api.websocket_progress.broadcast_to_analysis",
        new_callable=AsyncMock,
    ) as mock_broadcast:
        emit_agent_status(
            analysis_id="aid-1",
            agent_name="data_harvester",
            status="running",
            tool_call="sec_edgar",
        )
        await asyncio.sleep(0.05)
    mock_broadcast.assert_called_once()
    call_args = mock_broadcast.call_args[0]
    assert call_args[0] == "aid-1"
    assert call_args[1]["type"] == "agent_status"
    assert call_args[1]["agent_name"] == "data_harvester"
    assert call_args[1]["status"] == "running"
    assert call_args[1]["tool_call"] == "sec_edgar"


@pytest.mark.asyncio
async def test_emit_agent_status_without_tool_call() -> None:
    with patch(
        "backend.api.websocket_progress.broadcast_to_analysis",
        new_callable=AsyncMock,
    ) as mock_broadcast:
        emit_agent_status(
            analysis_id="aid-2",
            agent_name="judge_agent",
            status="completed",
        )
        await asyncio.sleep(0.05)
    mock_broadcast.assert_called_once()
    payload = mock_broadcast.call_args[0][1]
    assert payload["type"] == "agent_status"
    assert payload["agent_name"] == "judge_agent"
    assert payload["status"] == "completed"
    assert "tool_call" not in payload
