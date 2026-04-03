from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.tools.yfinance_client import (
    _fetch_ipo_price_history_sync,
    _is_plausible_ipo_date,
    _resolve_ipo_date_for_ticker_sync,
)


class TestIsPlausibleIpoDate:
    def test_rejects_dates_before_2000(self) -> None:
        assert _is_plausible_ipo_date(date(1999, 12, 31)) is False

    def test_rejects_1980s_date(self) -> None:
        assert _is_plausible_ipo_date(date(1985, 6, 15)) is False

    def test_accepts_boundary_date(self) -> None:
        assert _is_plausible_ipo_date(date(2000, 1, 1)) is True

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

    def test_rejects_implausible_ipoDate_string_and_falls_through(self) -> None:
        hist_mock = MagicMock()
        hist_mock.empty = True
        yf = self._make_yf({"ipoDate": "1985-01-01"})
        yf.Ticker.return_value.history.return_value = hist_mock
        with patch("importlib.import_module", return_value=yf):
            result = _resolve_ipo_date_for_ticker_sync("SPY")
        assert result is None

    def test_returns_plausible_date_from_firstTradeDateEpochUtc(self) -> None:
        epoch = int(datetime(2019, 6, 7, tzinfo=timezone.utc).timestamp())
        yf = self._make_yf({"firstTradeDateEpochUtc": epoch})
        with patch("importlib.import_module", return_value=yf):
            result = _resolve_ipo_date_for_ticker_sync("CRWD")
        assert result == date(2019, 6, 7)

    def test_rejects_implausible_firstTradeDateEpochUtc(self) -> None:
        epoch = int(datetime(1993, 1, 22, tzinfo=timezone.utc).timestamp())
        hist_mock = MagicMock()
        hist_mock.empty = True
        yf = self._make_yf({"firstTradeDateEpochUtc": epoch})
        yf.Ticker.return_value.history.return_value = hist_mock
        with patch("importlib.import_module", return_value=yf):
            result = _resolve_ipo_date_for_ticker_sync("MSFT")
        assert result is None

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

    def test_falls_back_to_history_and_rejects_implausible_date(self) -> None:
        first_date = datetime(1985, 3, 13, tzinfo=timezone.utc)
        hist_mock = MagicMock()
        hist_mock.empty = False
        hist_mock.index = [first_date]
        yf = self._make_yf({})
        yf.Ticker.return_value.history.return_value = hist_mock
        with patch("importlib.import_module", return_value=yf):
            result = _resolve_ipo_date_for_ticker_sync("OLD")
        assert result is None

    def test_empty_ticker_returns_none(self) -> None:
        with patch("importlib.import_module", return_value=MagicMock()):
            result = _resolve_ipo_date_for_ticker_sync("  ")
        assert result is None


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

    def test_implausible_ipo_price_returns_empty(self) -> None:
        yf = MagicMock()
        ticker_mock = MagicMock()
        ipo_date = date(2021, 5, 20)
        ticker_mock.history.return_value = self._make_history([0.001, 0.002], ipo_date)
        yf.Ticker.return_value = ticker_mock

        with patch("importlib.import_module", return_value=yf):
            result = _fetch_ipo_price_history_sync("SPAC", ipo_date)

        assert result["ipo_price"] is None
        assert result["current_price"] is None

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

    def test_boundary_price_exactly_050_is_accepted(self) -> None:
        yf = MagicMock()
        ticker_mock = MagicMock()
        ipo_date = date(2021, 1, 1)
        ticker_mock.history.return_value = self._make_history([0.50, 1.0], ipo_date)
        yf.Ticker.return_value = ticker_mock

        with patch("importlib.import_module", return_value=yf):
            result = _fetch_ipo_price_history_sync("TST", ipo_date)

        assert result["ipo_price"] == 0.50

    def test_empty_ticker_returns_empty(self) -> None:
        with patch("importlib.import_module", return_value=MagicMock()):
            result = _fetch_ipo_price_history_sync("", date(2021, 1, 1))
        assert result["ipo_price"] is None
