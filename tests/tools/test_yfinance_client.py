from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tools.yfinance_client import (
    _fetch_ipo_price_history_sync,
    _is_plausible_ipo_date,
    _resolve_ipo_date_for_ticker_sync,
    _resolve_symbol,
    resolve_ipo_date_for_ticker,
)


class TestIsPlausibleIpoDate:
    def test_rejects_dates_before_1980(self) -> None:
        assert _is_plausible_ipo_date(date(1979, 12, 31)) is False

    def test_accepts_1980s_date(self) -> None:
        assert _is_plausible_ipo_date(date(1985, 6, 15)) is True

    def test_accepts_boundary_date(self) -> None:
        assert _is_plausible_ipo_date(date(1980, 1, 1)) is True

    def test_accepts_modern_date(self) -> None:
        assert _is_plausible_ipo_date(date(2021, 5, 20)) is True


class TestResolveIpoDateForTickerSync:
    def _make_yf(self, info: dict, history_index: list | None = None) -> MagicMock:
        yf = MagicMock()
        ticker_mock = MagicMock()
        ticker_mock.info = info
        if history_index is not None:
            hist_mock = MagicMock()
            hist_mock.empty = len(history_index) == 0
            hist_mock.index = history_index
            ticker_mock.history.return_value = hist_mock
        else:
            hist_mock = MagicMock()
            hist_mock.empty = True
            ticker_mock.history.return_value = hist_mock
        yf.Ticker.return_value = ticker_mock
        return yf

    def test_returns_plausible_ipo_date_from_ipoDate_string(self) -> None:
        yf = self._make_yf({"ipoDate": "2021-05-20"})
        with patch("importlib.import_module", return_value=yf):
            result = _resolve_ipo_date_for_ticker_sync("NVDA")
        assert result == date(2021, 5, 20)

    def test_accepts_1980s_ipoDate_string(self) -> None:
        hist_mock = MagicMock()
        hist_mock.empty = True
        yf = self._make_yf({"ipoDate": "1985-01-01"})
        yf.Ticker.return_value.history.return_value = hist_mock
        with patch("importlib.import_module", return_value=yf):
            result = _resolve_ipo_date_for_ticker_sync("SPY")
        assert result == date(1985, 1, 1)

    def test_returns_plausible_date_from_firstTradeDateEpochUtc(self) -> None:
        epoch = int(datetime(2019, 6, 7, tzinfo=timezone.utc).timestamp())
        yf = self._make_yf({"firstTradeDateEpochUtc": epoch})
        with patch("importlib.import_module", return_value=yf):
            result = _resolve_ipo_date_for_ticker_sync("CRWD")
        assert result == date(2019, 6, 7)

    def test_accepts_1990s_firstTradeDateEpochUtc(self) -> None:
        epoch = int(datetime(1993, 1, 22, tzinfo=timezone.utc).timestamp())
        hist_mock = MagicMock()
        hist_mock.empty = True
        yf = self._make_yf({"firstTradeDateEpochUtc": epoch})
        yf.Ticker.return_value.history.return_value = hist_mock
        with patch("importlib.import_module", return_value=yf):
            result = _resolve_ipo_date_for_ticker_sync("MSFT")
        assert result == date(1993, 1, 22)

    def test_falls_back_to_history_and_accepts_plausible_date(self) -> None:
        first_date = datetime(2020, 9, 16, tzinfo=timezone.utc)
        hist_mock = MagicMock()
        hist_mock.empty = False
        hist_mock.index = [first_date]
        yf = self._make_yf({})
        yf.Ticker.return_value.history.return_value = hist_mock
        with patch("importlib.import_module", return_value=yf):
            result = _resolve_ipo_date_for_ticker_sync("SNOW")
        assert result == date(2020, 9, 16)

    def test_falls_back_to_history_and_accepts_1980s_date(self) -> None:
        first_date = datetime(1985, 3, 13, tzinfo=timezone.utc)
        hist_mock = MagicMock()
        hist_mock.empty = False
        hist_mock.index = [first_date]
        yf = self._make_yf({})
        yf.Ticker.return_value.history.return_value = hist_mock
        with patch("importlib.import_module", return_value=yf):
            result = _resolve_ipo_date_for_ticker_sync("OLD")
        assert result == date(1985, 3, 13)

    def test_empty_ticker_returns_none(self) -> None:
        with patch("importlib.import_module", return_value=MagicMock()):
            result = _resolve_ipo_date_for_ticker_sync("  ")
        assert result is None

    def test_maps_asx_suffix_to_ax_for_yahoo_ticker(self) -> None:
        yf = MagicMock()
        ticker_mock = MagicMock()
        ticker_mock.info = {"ipoDate": "2021-05-20"}
        hist_mock = MagicMock()
        hist_mock.empty = True
        ticker_mock.history.return_value = hist_mock
        yf.Ticker.return_value = ticker_mock
        with patch("importlib.import_module", return_value=yf):
            result = _resolve_ipo_date_for_ticker_sync("LYC.ASX")
        assert result == date(2021, 5, 20)
        yf.Ticker.assert_called_with("LYC.AX")


@pytest.mark.asyncio
async def test_resolve_ipo_date_for_ticker_retries_until_success() -> None:
    side_effects = [None, None, date(1997, 5, 15)]
    sleep_mock = AsyncMock()
    with (
        patch("backend.tools.yfinance_client._resolve_ipo_date_for_ticker_sync", side_effect=side_effects) as sync_mock,
        patch("backend.tools.yfinance_client.asyncio.sleep", sleep_mock),
    ):
        result = await resolve_ipo_date_for_ticker("AMZN")

    assert result == date(1997, 5, 15)
    assert sync_mock.call_count == 3
    assert sleep_mock.await_count == 2


@pytest.mark.asyncio
async def test_resolve_ipo_date_for_ticker_logs_when_retries_exhausted(caplog: pytest.LogCaptureFixture) -> None:
    sleep_mock = AsyncMock()
    with (
        patch("backend.tools.yfinance_client._resolve_ipo_date_for_ticker_sync", return_value=None) as sync_mock,
        patch("backend.tools.yfinance_client.asyncio.sleep", sleep_mock),
        caplog.at_level("WARNING"),
    ):
        result = await resolve_ipo_date_for_ticker("AMZN")

    assert result is None
    assert sync_mock.call_count == 3
    assert "Unable to resolve IPO date for ticker=AMZN after 3 attempts" in caplog.text


class TestResolveSymbol:
    def test_explicit_exchange_symbol_skips_search_when_info_validates(self) -> None:
        yf = MagicMock()
        ticker_mock = MagicMock()
        ticker_mock.info = {"symbol": "BARC.L", "quoteType": "EQUITY"}
        yf.Ticker.return_value = ticker_mock

        sym = _resolve_symbol(yf, "BARC.L")

        assert sym == "BARC.L"
        yf.Search.assert_not_called()

    def test_explicit_plain_ticker_skips_search_when_info_validates(self) -> None:
        yf = MagicMock()
        ticker_mock = MagicMock()
        ticker_mock.info = {"symbol": "PL", "quoteType": "EQUITY", "shortName": "Planet Labs"}
        yf.Ticker.return_value = ticker_mock

        sym = _resolve_symbol(yf, "PL")

        assert sym == "PL"
        yf.Search.assert_not_called()

    def test_explicit_symbol_falls_back_to_search_when_info_empty(self) -> None:
        yf = MagicMock()
        ticker_mock = MagicMock()
        ticker_mock.info = {}
        yf.Ticker.return_value = ticker_mock
        search = MagicMock()
        search.quotes = [{"symbol": "PL", "quoteType": "EQUITY"}]
        yf.Search.return_value = search

        sym = _resolve_symbol(yf, "PL")

        assert sym == "PL"
        yf.Search.assert_called_once()

    def test_company_name_uses_search(self) -> None:
        yf = MagicMock()
        ticker_mock = MagicMock()
        ticker_mock.info = {}
        yf.Ticker.return_value = ticker_mock
        search = MagicMock()
        search.quotes = [{"symbol": "BCS", "quoteType": "EQUITY"}]
        yf.Search.return_value = search

        sym = _resolve_symbol(yf, "Barclays PLC")

        assert sym == "BCS"

    def test_explicit_asx_suffix_tries_ax_alias(self) -> None:
        yf = MagicMock()

        def _ticker_side_effect(sym: str) -> MagicMock:
            m = MagicMock()
            if sym == "LYC.ASX":
                m.info = {}
            else:
                m.info = {"symbol": "LYC.AX", "quoteType": "EQUITY"}
            return m

        yf.Ticker.side_effect = _ticker_side_effect

        sym = _resolve_symbol(yf, "LYC.ASX")

        assert sym == "LYC.AX"
        yf.Search.assert_not_called()


class TestFetchIpoPriceHistorySync:
    def _make_history(self, prices: list[float], start_date: date) -> MagicMock:
        import pandas as pd

        dates = pd.date_range(start=start_date.isoformat(), periods=len(prices), freq="D", tz="UTC")
        df = pd.DataFrame({"Close": prices}, index=dates)
        return df

    def test_auto_adjust_false_passed_to_history(self) -> None:
        yf = MagicMock()
        ticker_mock = MagicMock()
        ipo_date = date(2021, 5, 20)
        ticker_mock.history.return_value = self._make_history([40.0, 42.0, 38.0], ipo_date)
        yf.Ticker.return_value = ticker_mock

        with patch("importlib.import_module", return_value=yf):
            _fetch_ipo_price_history_sync("NVDA", ipo_date)

        ticker_mock.history.assert_called_once_with(start=ipo_date.isoformat(), auto_adjust=False)

    def test_small_positive_split_adjusted_ipo_price_is_accepted(self) -> None:
        yf = MagicMock()
        ticker_mock = MagicMock()
        ipo_date = date(2021, 5, 20)
        ticker_mock.history.return_value = self._make_history([0.0979, 0.1200, 0.0850], ipo_date)
        yf.Ticker.return_value = ticker_mock

        with patch("importlib.import_module", return_value=yf):
            result = _fetch_ipo_price_history_sync("AMZN", ipo_date)

        assert result["ipo_price"] == 0.0979
        assert result["current_price"] == 0.085
        assert result["peak_price"] == 0.12
        assert result["trough_price"] == 0.085

    def test_valid_price_returned_correctly(self) -> None:
        yf = MagicMock()
        ticker_mock = MagicMock()
        ipo_date = date(2021, 9, 16)
        ticker_mock.history.return_value = self._make_history([40.0, 45.0, 38.0], ipo_date)
        yf.Ticker.return_value = ticker_mock

        with patch("importlib.import_module", return_value=yf):
            result = _fetch_ipo_price_history_sync("SNOW", ipo_date)

        assert result["ipo_price"] == 40.0
        assert result["current_price"] == 38.0
        assert result["peak_price"] == 45.0
        assert result["trough_price"] == 38.0

    def test_non_positive_ipo_price_returns_empty(self) -> None:
        yf = MagicMock()
        ticker_mock = MagicMock()
        ipo_date = date(2021, 1, 1)
        ticker_mock.history.return_value = self._make_history([0.0, 1.0], ipo_date)
        yf.Ticker.return_value = ticker_mock

        with patch("importlib.import_module", return_value=yf):
            result = _fetch_ipo_price_history_sync("TST", ipo_date)

        assert result["ipo_price"] is None
        assert result["current_price"] is None

    def test_empty_ticker_returns_empty(self) -> None:
        with patch("importlib.import_module", return_value=MagicMock()):
            result = _fetch_ipo_price_history_sync("", date(2021, 1, 1))
        assert result["ipo_price"] is None
