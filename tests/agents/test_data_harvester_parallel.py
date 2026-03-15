import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.data_harvester import DataHarvester, DataHarvesterInput
from backend.models.harvester_output import (
    CrunchbaseData,
    FredData,
    NewsArticle,
    SecFiling,
    TwitterData,
    TwitterSentimentScore,
    YahooFinanceData,
)


def _make_sec_edgar() -> list[SecFiling]:
    return [SecFiling(url="https://sec.gov/1", text="S-1", filing_type="S-1")]


def _make_news() -> list[NewsArticle]:
    return [
        NewsArticle(
            source="Reuters",
            title="IPO News",
            date=datetime.now(timezone.utc),
            content="...",
            url="https://example.com/1",
            is_primary_source=False,
        )
    ]


def _make_crunchbase() -> CrunchbaseData:
    return CrunchbaseData(total_raised=100.0, investors=["VC1"], last_valuation=500.0)


def _make_yahoo() -> YahooFinanceData:
    return YahooFinanceData(comparable_companies=["A", "B"], sector_90d_performance=12.5)


def _make_fred() -> FredData:
    return FredData(fed_funds_rate=5.25, market_conditions="Tight")


@pytest.fixture
def harvester() -> DataHarvester:
    return DataHarvester(
        sec_edgar=AsyncMock(return_value=_make_sec_edgar()),
        rss_feeds=AsyncMock(return_value=_make_news()),
        news_api=AsyncMock(return_value=_make_news()),
        crunchbase=AsyncMock(return_value=_make_crunchbase()),
        yahoo_finance=AsyncMock(return_value=_make_yahoo()),
        fred=AsyncMock(return_value=_make_fred()),
        twitter=AsyncMock(
            return_value=TwitterData(
                sentiment_score=TwitterSentimentScore(positive=0.2, negative=0.1, neutral=0.7),
                key_quotes=[],
            )
        ),
    )


@pytest.fixture
def payload() -> DataHarvesterInput:
    return DataHarvesterInput(
        analysis_id="test-id",
        company_name="SpaceX",
        complexity_tier="standard",
        active_sources=["sec_edgar", "rss_feeds", "news_api", "yahoo_finance", "fred"],
    )


@pytest.mark.asyncio
async def test_all_sources_succeed_assembles_output(
    harvester: DataHarvester, payload: DataHarvesterInput
) -> None:
    with (
        patch("backend.agents.data_harvester.save_harvester_output", new_callable=AsyncMock),
        patch("backend.agents.data_harvester.log_agent_run_start", new_callable=AsyncMock, return_value={"id": "run-1"}),
        patch("backend.agents.data_harvester.log_agent_run_completed", new_callable=AsyncMock),
    ):
        out = await harvester.run(payload)
    assert out.analysis_id == "test-id"
    harvester._sec_edgar.assert_awaited_once_with("SpaceX")
    harvester._rss_feeds.assert_awaited_once_with("SpaceX")
    harvester._news_api.assert_awaited_once_with("SpaceX")
    harvester._yahoo_finance.assert_awaited_once_with("SpaceX")
    harvester._fred.assert_awaited_once()


@pytest.mark.asyncio
async def test_sources_run_in_parallel(harvester: DataHarvester, payload: DataHarvesterInput) -> None:
    call_order: list[str] = []
    lock = asyncio.Lock()

    async def sec(*args: object, **kwargs: object) -> list[SecFiling]:
        async with lock:
            call_order.append("sec_start")
        await asyncio.sleep(0.03)
        async with lock:
            call_order.append("sec_end")
        return _make_sec_edgar()

    async def rss(*args: object, **kwargs: object) -> list[NewsArticle]:
        async with lock:
            call_order.append("rss_start")
        await asyncio.sleep(0.03)
        async with lock:
            call_order.append("rss_end")
        return _make_news()

    async def news(*args: object, **kwargs: object) -> list[NewsArticle]:
        async with lock:
            call_order.append("news_start")
        await asyncio.sleep(0.03)
        async with lock:
            call_order.append("news_end")
        return _make_news()

    harvester._sec_edgar = sec
    harvester._rss_feeds = rss
    harvester._news_api = news
    payload.active_sources = ["sec_edgar", "rss_feeds", "news_api"]

    with (
        patch("backend.agents.data_harvester.save_harvester_output", new_callable=AsyncMock),
        patch("backend.agents.data_harvester.log_agent_run_start", new_callable=AsyncMock, return_value={"id": "run-1"}),
        patch("backend.agents.data_harvester.log_agent_run_completed", new_callable=AsyncMock),
    ):
        await harvester.run(payload)

    starts = [i for i, x in enumerate(call_order) if x.endswith("_start")]
    ends = [i for i, x in enumerate(call_order) if x.endswith("_end")]
    assert len(starts) == 3 and len(ends) == 3
    assert max(starts) < min(ends)


@pytest.mark.asyncio
async def test_partial_failure_continues_with_available_data(
    harvester: DataHarvester, payload: DataHarvesterInput
) -> None:
    harvester._crunchbase = AsyncMock(side_effect=RuntimeError("Crunchbase API down"))
    payload.active_sources = ["sec_edgar", "news_api", "crunchbase"]

    with (
        patch("backend.agents.data_harvester.save_harvester_output", new_callable=AsyncMock) as save_mock,
        patch("backend.agents.data_harvester.log_agent_run_start", new_callable=AsyncMock, return_value={"id": "run-1"}),
        patch("backend.agents.data_harvester.log_agent_run_completed", new_callable=AsyncMock),
    ):
        await harvester.run(payload)

    saved = save_mock.call_args.kwargs["output"]
    assert "sec_edgar" in saved["sources_active"]
    assert "news_api" in saved["sources_active"]
    assert "crunchbase" not in saved["sources_active"]
    assert len(saved["sources_failed"]) == 1
    assert saved["sources_failed"][0]["source"] == "crunchbase"
    assert "Crunchbase API down" in saved["sources_failed"][0]["reason"]


@pytest.mark.asyncio
async def test_all_sources_fail_raises(harvester: DataHarvester, payload: DataHarvesterInput) -> None:
    harvester._sec_edgar = AsyncMock(side_effect=RuntimeError("SEC down"))
    harvester._news_api = AsyncMock(side_effect=RuntimeError("NewsAPI down"))
    harvester._crunchbase = AsyncMock(side_effect=RuntimeError("Crunchbase down"))
    payload.active_sources = ["sec_edgar", "news_api", "crunchbase"]

    with (
        patch("backend.agents.data_harvester.log_agent_run_start", new_callable=AsyncMock, return_value={"id": "run-1"}),
        patch("backend.agents.data_harvester.log_agent_run_failed", new_callable=AsyncMock),
    ):
        with pytest.raises(RuntimeError, match="All sources failed"):
            await harvester.run(payload)
