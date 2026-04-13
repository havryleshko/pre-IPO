import asyncio
from datetime import date
from unittest.mock import patch
from xml.etree import ElementTree

import pytest

from backend.tools.sec_edgar_client import (
    _issuer_name_match,
    _resolve_primary_document_url,
    fetch_post_ipo_filings,
    fetch_sec_edgar,
    resolve_ticker_from_input,
    resolve_ticker_from_name,
)


def test_resolve_primary_document_url_prefers_matching_form_document() -> None:
    index_url = "https://www.sec.gov/Archives/edgar/data/1769628/000119312525058309/0001193125-25-058309-index.htm"
    index_html = """
    <html>
      <body>
        <table class="tableFile" summary="Document Format Files">
          <tr>
            <th>Seq</th><th>Description</th><th>Document</th><th>Type</th>
          </tr>
          <tr>
            <td>1</td><td>S-1/A</td><td><a href="d899798ds1a.htm">d899798ds1a.htm</a></td><td>S-1/A</td>
          </tr>
          <tr>
            <td>2</td><td>Exhibit</td><td><a href="d899798dex11.htm">d899798dex11.htm</a></td><td>EX-1.1</td>
          </tr>
        </table>
      </body>
    </html>
    """

    resolved = _resolve_primary_document_url(index_url, "S-1/A", index_html)

    assert (
        resolved
        == "https://www.sec.gov/Archives/edgar/data/1769628/000119312525058309/d899798ds1a.htm"
    )


def test_resolve_primary_document_url_falls_back_to_first_html_document() -> None:
    index_url = "https://www.sec.gov/Archives/edgar/data/1769628/000119312525058309/0001193125-25-058309-index.htm"
    index_html = """
    <html>
      <body>
        <table class="tableFile" summary="Document Format Files">
          <tr>
            <th>Seq</th><th>Description</th><th>Document</th><th>Type</th>
          </tr>
          <tr>
            <td>1</td><td>Main filing</td><td><a href="primary.htm">primary.htm</a></td><td>10-K</td>
          </tr>
          <tr>
            <td>2</td><td>Text</td><td><a href="primary.txt">primary.txt</a></td><td>TXT</td>
          </tr>
        </table>
      </body>
    </html>
    """

    resolved = _resolve_primary_document_url(index_url, "S-1", index_html)

    assert resolved == "https://www.sec.gov/Archives/edgar/data/1769628/000119312525058309/primary.htm"


def test_issuer_name_match_strips_suffixes_and_punctuation() -> None:
    matches, score, requested_norm, issuer_norm = _issuer_name_match(
        "Acme, Inc.",
        "ACME INCORPORATED",
    )

    assert matches is True
    assert score == 1.0
    assert requested_norm == "acme"
    assert issuer_norm == "acme"


def test_issuer_name_match_allows_subset_overlap() -> None:
    matches, score, requested_norm, issuer_norm = _issuer_name_match(
        "Acme Holdings",
        "Acme Holdings Group, Inc.",
    )

    assert matches is True
    assert score >= 0.6
    assert requested_norm == "acme"
    assert issuer_norm == "acme"


def test_issuer_name_match_rejects_mismatch() -> None:
    matches, score, requested_norm, issuer_norm = _issuer_name_match(
        "Acme",
        "Beta Corp",
    )

    assert matches is False
    assert score < 0.6
    assert requested_norm == "acme"
    assert issuer_norm == "beta"


def test_fetch_sec_edgar_rejects_mismatched_issuer_after_resolution() -> None:
    async def _immediate_to_thread(fn, /, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("backend.tools.sec_edgar_client.asyncio.to_thread", new=_immediate_to_thread), patch(
        "backend.tools.sec_edgar_client._lookup_company_cik", return_value="0000000001"
    ), patch(
        "backend.tools.sec_edgar_client._resolve_conformed_issuer_name", return_value="Beta Corp"
    ):
        filings = asyncio.run(fetch_sec_edgar("Acme"))

    assert filings == []


def test_fetch_post_ipo_filings_returns_first_10k_text() -> None:
    async def _immediate_to_thread(fn, /, *args, **kwargs):
        return fn(*args, **kwargs)

    def _mock_fetch_feed(url: str) -> ElementTree.Element:
        if "type=10-K" in url:
            return _feed_xml(
                _filing_entry("10-K", "https://example.com/pre-ipo-10k", "2023-09-01"),
                _filing_entry("10-K", "https://example.com/first-10k", "2024-05-15"),
                _filing_entry("10-K/A", "https://example.com/later-10ka", "2024-06-01"),
            )
        return _feed_xml(
            _filing_entry("10-Q", "https://example.com/q1", "2024-03-01"),
            _filing_entry("10-Q", "https://example.com/q2", "2024-08-01"),
        )

    def _mock_primary_text(index_url: str, filing_type: str) -> tuple[str, str]:
        return index_url, f"{filing_type} text for {index_url}"

    with patch("backend.tools.sec_edgar_client.asyncio.to_thread", new=_immediate_to_thread), patch(
        "backend.tools.sec_edgar_client._lookup_cik_from_ticker", return_value="0001973239"
    ), patch(
        "backend.tools.sec_edgar_client._fetch_feed", side_effect=_mock_fetch_feed
    ), patch(
        "backend.tools.sec_edgar_client._get_primary_filing_text", side_effect=_mock_primary_text
    ):
        filing_text = asyncio.run(fetch_post_ipo_filings("ARM", date(2023, 9, 14)))

    assert filing_text == "10-K text for https://example.com/first-10k"


def test_fetch_post_ipo_filings_returns_none_when_only_10qs_exist() -> None:
    async def _immediate_to_thread(fn, /, *args, **kwargs):
        return fn(*args, **kwargs)

    def _mock_fetch_feed(_: str) -> ElementTree.Element:
        return _feed_xml(
            _filing_entry("10-Q", "https://example.com/q1", "2024-03-01"),
            _filing_entry("10-Q", "https://example.com/q2", "2024-08-01"),
        )

    with patch("backend.tools.sec_edgar_client.asyncio.to_thread", new=_immediate_to_thread), patch(
        "backend.tools.sec_edgar_client._lookup_cik_from_ticker", return_value="0001973239"
    ), patch(
        "backend.tools.sec_edgar_client._fetch_feed", side_effect=_mock_fetch_feed
    ), patch(
        "backend.tools.sec_edgar_client._get_primary_filing_text"
    ) as get_primary_text:
        filing_text = asyncio.run(fetch_post_ipo_filings("ARM", date(2023, 9, 14)))

    assert filing_text is None
    get_primary_text.assert_not_called()


def test_fetch_post_ipo_filings_excludes_pre_ipo_filings() -> None:
    async def _immediate_to_thread(fn, /, *args, **kwargs):
        return fn(*args, **kwargs)

    def _mock_fetch_feed(url: str) -> ElementTree.Element:
        if "type=10-K" in url:
            return _feed_xml(_filing_entry("10-K", "https://example.com/pre-ipo-10k", "2023-09-01"))
        return _feed_xml(_filing_entry("10-Q", "https://example.com/q1", "2024-03-01"))

    with patch("backend.tools.sec_edgar_client.asyncio.to_thread", new=_immediate_to_thread), patch(
        "backend.tools.sec_edgar_client._lookup_cik_from_ticker", return_value="0001973239"
    ), patch(
        "backend.tools.sec_edgar_client._fetch_feed", side_effect=_mock_fetch_feed
    ), patch(
        "backend.tools.sec_edgar_client._get_primary_filing_text"
    ) as get_primary_text:
        filing_text = asyncio.run(fetch_post_ipo_filings("ARM", date(2023, 9, 14)))

    assert filing_text is None
    get_primary_text.assert_not_called()


@pytest.mark.parametrize(
    ("company_name", "issuer_name", "expected_ticker"),
    [
        ("Arm Holdings", "Arm Holdings plc", "ARM"),
        ("Reddit", "Reddit, Inc.", "RDDT"),
        ("Maplebear", "Maplebear Inc.", "CART"),
    ],
)
def test_resolve_ticker_from_name_returns_expected_match(
    company_name: str,
    issuer_name: str,
    expected_ticker: str,
) -> None:
    async def _immediate_to_thread(fn, /, *args, **kwargs):
        return fn(*args, **kwargs)

    ticker_payload = {
        "0": {"title": "Arm Holdings plc", "ticker": "ARM", "cik_str": 1973239},
        "1": {"title": "Reddit, Inc.", "ticker": "RDDT", "cik_str": 1713445},
        "2": {"title": "Maplebear Inc.", "ticker": "CART", "cik_str": 1579091},
    }

    def _mock_issuer_lookup(cik: str) -> str:
        return {
            "0001973239": "Arm Holdings plc",
            "0001713445": "Reddit, Inc.",
            "0001579091": "Maplebear Inc.",
        }[cik]

    with patch("backend.tools.sec_edgar_client.asyncio.to_thread", new=_immediate_to_thread), patch(
        "backend.tools.sec_edgar_client._fetch_json", return_value=ticker_payload
    ), patch(
        "backend.tools.sec_edgar_client._resolve_conformed_issuer_name", side_effect=_mock_issuer_lookup
    ):
        ticker = asyncio.run(resolve_ticker_from_name(company_name))

    assert ticker == expected_ticker


def test_resolve_ticker_from_name_raises_on_issuer_mismatch() -> None:
    async def _immediate_to_thread(fn, /, *args, **kwargs):
        return fn(*args, **kwargs)

    ticker_payload = {
        "0": {"title": "Acme Inc.", "ticker": "ACME", "cik_str": 1},
    }

    with patch("backend.tools.sec_edgar_client.asyncio.to_thread", new=_immediate_to_thread), patch(
        "backend.tools.sec_edgar_client._fetch_json", return_value=ticker_payload
    ), patch(
        "backend.tools.sec_edgar_client._resolve_conformed_issuer_name", return_value="Beta Corp"
    ):
        with pytest.raises(RuntimeError, match="SEC issuer mismatch"):
            asyncio.run(resolve_ticker_from_name("Acme"))


def test_resolve_ticker_from_input_accepts_direct_ticker() -> None:
    async def _immediate_to_thread(fn, /, *args, **kwargs):
        return fn(*args, **kwargs)

    ticker_payload = {
        "0": {"title": "Rocket Lab USA, Inc.", "ticker": "RKLB", "cik_str": 1819994},
    }

    with patch("backend.tools.sec_edgar_client.asyncio.to_thread", new=_immediate_to_thread), patch(
        "backend.tools.sec_edgar_client._fetch_json", return_value=ticker_payload
    ) as fetch_json:
        ticker = asyncio.run(resolve_ticker_from_input("RKLB"))

    assert ticker == "RKLB"
    fetch_json.assert_not_called()


def test_resolve_ticker_from_input_passes_through_pl_without_sec_name_resolution() -> None:
    async def _immediate_to_thread(fn, /, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("backend.tools.sec_edgar_client.asyncio.to_thread", new=_immediate_to_thread), patch(
        "backend.tools.sec_edgar_client._fetch_json"
    ) as fetch_json:
        ticker = asyncio.run(resolve_ticker_from_input("PL"))

    assert ticker == "PL"
    fetch_json.assert_not_called()


def test_resolve_ticker_from_input_passes_through_exchange_qualified_symbol() -> None:
    async def _immediate_to_thread(fn, /, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("backend.tools.sec_edgar_client.asyncio.to_thread", new=_immediate_to_thread), patch(
        "backend.tools.sec_edgar_client._fetch_json"
    ) as fetch_json:
        barc = asyncio.run(resolve_ticker_from_input("BARC.L"))
        lyc = asyncio.run(resolve_ticker_from_input("LYC.ASX"))

    assert barc == "BARC.L"
    assert lyc == "LYC.ASX"
    fetch_json.assert_not_called()


def test_resolve_ticker_from_input_barclays_still_uses_name_resolution() -> None:
    async def _immediate_to_thread(fn, /, *args, **kwargs):
        return fn(*args, **kwargs)

    ticker_payload = {
        "0": {"title": "Barclays PLC", "ticker": "BCS", "cik_str": 3120709},
    }

    def _mock_issuer_lookup(cik: str) -> str:
        return {"0003120709": "Barclays PLC"}[cik]

    with patch("backend.tools.sec_edgar_client.asyncio.to_thread", new=_immediate_to_thread), patch(
        "backend.tools.sec_edgar_client._fetch_json", return_value=ticker_payload
    ), patch(
        "backend.tools.sec_edgar_client._resolve_conformed_issuer_name", side_effect=_mock_issuer_lookup
    ):
        ticker = asyncio.run(resolve_ticker_from_input("Barclays"))

    assert ticker == "BCS"


def test_fetch_sec_edgar_accepts_direct_ticker_input() -> None:
    async def _immediate_to_thread(fn, /, *args, **kwargs):
        return fn(*args, **kwargs)

    ticker_payload = {
        "0": {"title": "Rocket Lab USA, Inc.", "ticker": "RKLB", "cik_str": 1819994},
    }

    def _mock_fetch_feed(_: str) -> ElementTree.Element:
        return _feed_xml(_filing_entry("S-1", "https://example.com/rklb-s1", "2021-07-15"))

    def _mock_primary_text(index_url: str, filing_type: str) -> tuple[str, str]:
        return index_url, f"{filing_type} text for {index_url}"

    with patch("backend.tools.sec_edgar_client.asyncio.to_thread", new=_immediate_to_thread), patch(
        "backend.tools.sec_edgar_client._fetch_json", return_value=ticker_payload
    ), patch(
        "backend.tools.sec_edgar_client._resolve_conformed_issuer_name", return_value="Rocket Lab USA, Inc."
    ), patch(
        "backend.tools.sec_edgar_client._fetch_feed", side_effect=_mock_fetch_feed
    ), patch(
        "backend.tools.sec_edgar_client._get_primary_filing_text", side_effect=_mock_primary_text
    ):
        filings = asyncio.run(fetch_sec_edgar("RKLB"))

    assert len(filings) == 1
    assert filings[0].filing_type == "S-1"
    assert filings[0].url == "https://example.com/rklb-s1"


def _feed_xml(*entries: str) -> ElementTree.Element:
    return ElementTree.fromstring(
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        + "".join(entries)
        + "</feed>"
    )


def _filing_entry(filing_type: str, filing_url: str, filing_date: str) -> str:
    return f"""
    <entry>
      <content>
        <filing-type>{filing_type}</filing-type>
        <filing-href>{filing_url}</filing-href>
        <filing-date>{filing_date}</filing-date>
      </content>
    </entry>
    """
