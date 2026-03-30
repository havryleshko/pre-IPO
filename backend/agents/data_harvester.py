import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel

from backend.database.queries import save_harvester_output
from backend.models.analysis import AnalysisComplexityTier
from backend.models.harvester_output import (
    CrunchbaseData,
    FredData,
    HarvesterOutput,
    NewsArticle,
    SecFiling,
    SourceFailure,
    TwitterData,
    TwitterSentimentScore,
    YahooFinanceData,
)
from backend.services.agent_run_logger import (
    log_agent_run_completed,
    log_agent_run_failed,
    log_agent_run_start,
)
from backend.tools.sec_edgar_client import fetch_post_ipo_filings
from backend.api.websocket_progress import emit_agent_status

logger = logging.getLogger(__name__)


def _ipo_history_json_safe(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data:
        return None
    out = dict(data)
    lcd = out.get("lock_up_cliff_date")
    if isinstance(lcd, (date, datetime)):
        out["lock_up_cliff_date"] = lcd.isoformat() if isinstance(lcd, date) else lcd.date().isoformat()
    return out


class DataHarvesterInput(BaseModel):
    analysis_id: str
    company_name: str
    complexity_tier: AnalysisComplexityTier
    active_sources: list[str]
    task_boundaries: str = ""
    ticker: str | None = None
    ipo_date: date | None = None
    ipo_price_history: dict[str, Any] | None = None


class DataHarvesterOutput(BaseModel):
    analysis_id: str


class SecEdgarFetcher(Protocol):
    async def __call__(self, company_name: str) -> list[SecFiling]: ...


class RssFetcher(Protocol):
    async def __call__(self, company_name: str) -> list[NewsArticle]: ...


class NewsApiFetcher(Protocol):
    async def __call__(self, company_name: str) -> list[NewsArticle]: ...


class CrunchbaseFetcher(Protocol):
    async def __call__(self, company_name: str) -> CrunchbaseData: ...


class YahooFinanceFetcher(Protocol):
    async def __call__(self, company_name: str) -> YahooFinanceData: ...


class FredFetcher(Protocol):
    async def __call__(self) -> FredData: ...


class TwitterFetcher(Protocol):
    async def __call__(self, company_name: str) -> TwitterData: ...


_EMPTY_CRUNCHBASE = CrunchbaseData()
_EMPTY_YAHOO = YahooFinanceData()
_EMPTY_FRED = FredData()
_EMPTY_TWITTER_SENTIMENT = TwitterSentimentScore(positive=0.0, negative=0.0, neutral=1.0)


class DataHarvester:
    def __init__(
        self,
        sec_edgar: SecEdgarFetcher,
        rss_feeds: RssFetcher,
        news_api: NewsApiFetcher,
        crunchbase: CrunchbaseFetcher,
        yahoo_finance: YahooFinanceFetcher,
        fred: FredFetcher,
        twitter: TwitterFetcher,
    ) -> None:
        self._sec_edgar = sec_edgar
        self._rss_feeds = rss_feeds
        self._news_api = news_api
        self._crunchbase = crunchbase
        self._yahoo_finance = yahoo_finance
        self._fred = fred
        self._twitter = twitter

    async def run(self, payload: DataHarvesterInput) -> DataHarvesterOutput:
        run_record = await log_agent_run_start(
            analysis_id=payload.analysis_id,
            agent_name="data_harvester",
            input_reference=f"company={payload.company_name} tier={payload.complexity_tier}",
        )
        run_id: str = str(run_record["id"]) if run_record else ""

        try:
            output = await self._fetch_and_assemble(payload)
        except Exception as exc:
            await log_agent_run_failed(run_id=run_id, error_message=str(exc))
            raise

        await save_harvester_output(
            analysis_id=payload.analysis_id,
            output=output.model_dump(mode="json"),
        )
        await log_agent_run_completed(
            run_id=run_id,
            output_reference=f"analysis_id={payload.analysis_id}",
        )
        return DataHarvesterOutput(analysis_id=payload.analysis_id)

    async def _fetch_and_assemble(self, payload: DataHarvesterInput) -> HarvesterOutput:
        active = set(payload.active_sources)
        source_names: list[str] = []
        coroutines: list[Any] = []

        async def _wrap_source(source_name: str, coro: Any) -> Any:
            emit_agent_status(
                analysis_id=payload.analysis_id,
                agent_name="single_agent",
                status="running",
                tool_call=source_name,
            )
            return await coro

        if "sec_edgar" in active:
            source_names.append("sec_edgar")
            coroutines.append(_wrap_source("sec_edgar", self._sec_edgar(payload.company_name)))

        if "rss_feeds" in active:
            source_names.append("rss_feeds")
            coroutines.append(_wrap_source("rss_feeds", self._rss_feeds(payload.company_name)))

        if "news_api" in active:
            source_names.append("news_api")
            coroutines.append(_wrap_source("news_api", self._news_api(payload.company_name)))

        if "crunchbase" in active:
            source_names.append("crunchbase")
            coroutines.append(_wrap_source("crunchbase", self._crunchbase(payload.company_name)))

        if "yahoo_finance" in active:
            source_names.append("yahoo_finance")
            coroutines.append(_wrap_source("yahoo_finance", self._yahoo_finance(payload.company_name)))

        if "fred" in active:
            source_names.append("fred")
            coroutines.append(_wrap_source("fred", self._fred()))

        if "twitter" in active:
            source_names.append("twitter")
            coroutines.append(_wrap_source("twitter", self._twitter(payload.company_name)))

        raw_results = await asyncio.gather(*coroutines, return_exceptions=True)

        sec_filings: list[SecFiling] = []
        news_articles: list[NewsArticle] = []
        crunchbase_data: CrunchbaseData = _EMPTY_CRUNCHBASE
        yahoo_finance_data: YahooFinanceData = _EMPTY_YAHOO
        fred_data: FredData = _EMPTY_FRED
        twitter_data: TwitterData | None = None
        sources_active: list[str] = []
        sources_failed: list[SourceFailure] = []

        for name, result in zip(source_names, raw_results):
            if isinstance(result, Exception):
                logger.warning("Source %s failed: %s", name, result)
                sources_failed.append(SourceFailure(source=name, reason=str(result)))
                continue

            sources_active.append(name)

            if name == "sec_edgar":
                sec_filings = result
            elif name in ("rss_feeds", "news_api"):
                news_articles.extend(result)
            elif name == "crunchbase":
                crunchbase_data = result
            elif name == "yahoo_finance":
                yahoo_finance_data = result
            elif name == "fred":
                fred_data = result
            elif name == "twitter":
                twitter_data = result

        if not sources_active:
            raise RuntimeError(
                f"All sources failed for analysis_id={payload.analysis_id}: "
                + ", ".join(f.source for f in sources_failed)
            )

        post_ipo_10k: str | None = None
        if payload.ticker and payload.ipo_date:
            try:
                ten_k_text = await fetch_post_ipo_filings(payload.ticker, payload.ipo_date)
            except Exception as exc:
                logger.warning(
                    "Post-IPO 10-K fetch failed for analysis_id=%s: %s",
                    payload.analysis_id,
                    exc,
                )
                ten_k_text = None
            if isinstance(ten_k_text, str) and ten_k_text.strip():
                post_ipo_10k = ten_k_text.strip()
                sec_filings = [
                    *sec_filings,
                    SecFiling(
                        url="https://www.sec.gov/edgar/post-ipo-10k",
                        text=post_ipo_10k,
                        filing_type="10-K",
                    ),
                ]

        return HarvesterOutput(
            company_name=payload.company_name,
            complexity_tier=payload.complexity_tier,
            sec_filings=sec_filings,
            news_articles=news_articles,
            crunchbase_data=crunchbase_data,
            yahoo_finance_data=yahoo_finance_data,
            fred_data=fred_data,
            twitter_data=twitter_data,
            sources_active=sources_active,
            sources_failed=sources_failed,
            harvested_at=datetime.now(timezone.utc),
            ipo_price_history=_ipo_history_json_safe(payload.ipo_price_history),
            post_ipo_10k=post_ipo_10k,
        )
