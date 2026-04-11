from __future__ import annotations

import os

import httpx

from tui.types import AnalysisOutputsResponse, CreateAnalysisResponse

_DEFAULT_API_BASE = "http://127.0.0.1:8000"


def default_api_base() -> str:
    return os.environ.get("PREIPO_API_URL", _DEFAULT_API_BASE).rstrip("/")


class PreipoHttpClient:
    def __init__(self, api_base: str | None = None, *, timeout: float = 60.0) -> None:
        self._api_base = (api_base or default_api_base()).rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    @property
    def api_base(self) -> str:
        return self._api_base

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PreipoHttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def create_analysis(self, company_name: str) -> CreateAnalysisResponse:
        r = self._client.post(
            f"{self._api_base}/analyses",
            json={"company_name": company_name},
        )
        r.raise_for_status()
        return CreateAnalysisResponse.model_validate(r.json())

    def get_analysis(self, analysis_id: str) -> AnalysisOutputsResponse:
        r = self._client.get(f"{self._api_base}/analyses/{analysis_id}")
        r.raise_for_status()
        return AnalysisOutputsResponse.model_validate(r.json())

    def fetch_openapi(self) -> None:
        r = self._client.get(f"{self._api_base}/openapi.json")
        r.raise_for_status()
