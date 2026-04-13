# Ticker resolution smoke (2026-04-13)

Local run: `PYTHONPATH=. python` calling `resolve_ticker_from_input`, `_resolve_symbol`, `_resolve_ipo_date_for_ticker_sync` against live SEC JSON and Yahoo (yfinance).

| input | SEC `resolve_ticker_from_input` | Yahoo `_resolve_symbol` | `_resolve_ipo_date_for_ticker_sync` |
| --- | --- | --- | --- |
| BARC.L | BARC.L | BARC.L | 1988-07-01 |
| LYC.ASX | LYC.ASX | LYC.AX (Yahoo has no `.ASX`; fetch maps to `.AX`) | 1999-06-10 |
| PL | PL | PL | 2021-04-26 |

Full `preipo analyze` / DB result row was not run in this pass; resolver + IPO date checks only.
