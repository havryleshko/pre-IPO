import asyncio
from unittest.mock import patch

from backend.tools.sec_edgar_client import _issuer_name_match, _resolve_primary_document_url
from backend.tools.sec_edgar_client import fetch_sec_edgar


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
