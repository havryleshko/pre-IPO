from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.data_harvester import DataHarvester, DataHarvesterInput
from backend.models.harvester_output import CrunchbaseData, FredData, NewsArticle, SecFiling, TwitterData, YahooFinanceData


@pytest.mark.asyncio
async def test_data_harvester_emits_tool_call_per_source() -> None:
    async def sec(company: str) -> list[SecFiling]:
        await asyncio.sleep(0.01)
        return []

    async def rss(company: str) -> list[NewsArticle]:
        await asyncio.sleep(0.01)
        return []

    async def news(company: str) -> list[NewsArticle]:
        await asyncio.sleep(0.01)
        return []

    async def cb(company: str) -> CrunchbaseData:
        await asyncio.sleep(0.01)
        return CrunchbaseData()

    async def yf(company: str) -> YahooFinanceData:
        await asyncio.sleep(0.01)
        return YahooFinanceData()

    async def fred() -> FredData:
        await asyncio.sleep(0.01)
        return FredData()

    async def tw(company: str) -> TwitterData:
        await asyncio.sleep(0.01)
        return TwitterData()

    harvester = DataHarvester(sec_edgar=sec, rss_feeds=rss, news_api=news, crunchbase=cb, yahoo_finance=yf, fred=fred, twitter=tw)

    with (
        patch("backend.agents.data_harvester.save_harvester_output", new_callable=AsyncMock),
        patch("backend.agents.data_harvester.log_agent_run_start", new_callable=AsyncMock, return_value={"id": "rid"}),
        patch("backend.agents.data_harvester.log_agent_run_completed", new_callable=AsyncMock),
        patch("backend.agents.data_harvester.log_agent_run_failed", new_callable=AsyncMock),
        patch("backend.agents.data_harvester.emit_agent_status") as emit_mock,
    ):
        await harvester.run(
            DataHarvesterInput(
                analysis_id="aid-1",
                company_name="TestCo",
                complexity_tier="standard",
                active_sources=["sec_edgar", "rss_feeds", "news_api", "crunchbase", "yahoo_finance", "fred", "twitter"],
            )
        )

    tool_calls = [kwargs.get("tool_call") for _, kwargs in emit_mock.call_args_list]
    assert "sec_edgar" in tool_calls
    assert "rss_feeds" in tool_calls
    assert "news_api" in tool_calls
    assert "crunchbase" in tool_calls
    assert "yahoo_finance" in tool_calls
    assert "fred" in tool_calls
    assert "twitter" in tool_calls

