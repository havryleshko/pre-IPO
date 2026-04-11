from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator, Literal

import httpx
import websockets

from tui.export import export_all
from tui.types import AnalysisOutputsResponse, CreateAnalysisResponse, ProgressEvent, SingleAgentResult


def _default_api_base() -> str:
    return os.environ.get("PREIPO_API_URL", "http://127.0.0.1:8000").rstrip("/")


def _default_ws_base() -> str:
    return os.environ.get("PREIPO_WS_URL", "ws://127.0.0.1:8000").rstrip("/")


class ApiClient:
    def __init__(self, api_base: str | None = None, ws_base: str | None = None) -> None:
        self._api_base = api_base or _default_api_base()
        self._ws_base = ws_base or _default_ws_base()
        self._http = httpx.AsyncClient(timeout=60.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def create_analysis(self, company_name: str) -> CreateAnalysisResponse:
        r = await self._http.post(
            f"{self._api_base}/analyses",
            json={"company_name": company_name},
        )
        r.raise_for_status()
        return CreateAnalysisResponse.model_validate(r.json())

    async def get_analysis(self, analysis_id: str) -> AnalysisOutputsResponse:
        r = await self._http.get(f"{self._api_base}/analyses/{analysis_id}")
        r.raise_for_status()
        return AnalysisOutputsResponse.model_validate(r.json())

    async def progress_events(self, analysis_id: str) -> AsyncIterator[ProgressEvent]:
        url = f"{self._ws_base}/analyses/{analysis_id}/progress"
        async with websockets.connect(url) as ws:
            await ws.send("ping")
            async for raw in ws:
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                try:
                    yield ProgressEvent.model_validate(payload)
                except Exception:
                    continue

    async def export_all(self, analysis_id: str, result: SingleAgentResult) -> None:
        export_all(analysis_id=analysis_id, result=result)

