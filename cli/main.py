from __future__ import annotations

import argparse
import logging
import os
import sys
import time

import httpx

from cli.http_client import PreipoHttpClient, default_api_base
from tui.export import export_all
from tui.render import render_result_cli

_TERMINAL_STATUSES = frozenset({"failed", "completed", "completed_with_flags"})


def _configure_logging(*, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stderr)


def _apply_api_url_to_env(api_url: str) -> None:
    base = api_url.rstrip("/")
    os.environ["PREIPO_API_URL"] = base
    if base.startswith("https://"):
        os.environ["PREIPO_WS_URL"] = "wss://" + base.removeprefix("https://")
    elif base.startswith("http://"):
        os.environ["PREIPO_WS_URL"] = "ws://" + base.removeprefix("http://")


def _cmd_doctor(api_base: str, log: logging.Logger) -> int:
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{api_base}/openapi.json")
            r.raise_for_status()
    except Exception as exc:
        log.error("API not reachable at %s: %s", api_base, exc)
        return 1
    log.info("API reachable at %s", api_base)
    return 0


def _terminal_exit_code(status: str) -> int:
    return 1 if status == "failed" else 0


def _cmd_analyze(
    api_base: str,
    company_name: str,
    *,
    timeout_sec: float,
    interval_sec: float,
    json_mode: bool,
    show_id: bool,
    log: logging.Logger,
) -> int:
    with PreipoHttpClient(api_base=api_base) as http:
        try:
            created = http.create_analysis(company_name)
        except Exception as exc:
            log.error("Create analysis failed: %s", exc)
            return 1
        aid = created.analysis_id
        if show_id:
            log.info("analysis_id=%s", aid)
        deadline = time.monotonic() + timeout_sec
        try:
            data = http.get_analysis(aid)
        except Exception as exc:
            log.error("Fetch analysis failed for analysis_id=%s: %s", aid, exc)
            return 1
        while data.status not in _TERMINAL_STATUSES:
            if time.monotonic() >= deadline:
                log.error("Timed out after %s seconds (last status=%s)", timeout_sec, data.status)
                return 2
            time.sleep(interval_sec)
            try:
                data = http.get_analysis(aid)
            except Exception as exc:
                log.error("Polling failed for analysis_id=%s: %s", aid, exc)
                return 1
        if json_mode:
            sys.stdout.write(data.model_dump_json(indent=2) + "\n")
            return _terminal_exit_code(data.status)
        if data.analysis_result is None:
            log.error(
                "No structured analysis_result (status=%s). Use --json for full response or check API logs.",
                data.status,
            )
            return 1
        sys.stdout.write(render_result_cli(data.analysis_result))
        return _terminal_exit_code(data.status)


def _cmd_export(api_base: str, analysis_id: str, output_dir: str, log: logging.Logger) -> int:
    with PreipoHttpClient(api_base=api_base) as http:
        try:
            data = http.get_analysis(analysis_id)
        except Exception as exc:
            log.error("Fetch analysis failed: %s", exc)
            return 1
    if data.analysis_result is None:
        log.error("No analysis_result to export for analysis_id=%s (status=%s)", analysis_id, data.status)
        return 1
    try:
        export_all(analysis_id=analysis_id, result=data.analysis_result, base_dir=output_dir)
    except Exception as exc:
        log.error("Export failed: %s", exc)
        return 1
    log.info("Exported to %s/%s/", output_dir, analysis_id)
    return 0


def _cmd_tui() -> int:
    from tui.app import run

    run()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="preipo",
        description="pre-IPO CLI — talks to the pre-IPO API (start the API and Postgres separately).",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        metavar="URL",
        help="API base URL (default: PREIPO_API_URL or http://127.0.0.1:8000)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging on stderr")
    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser("doctor", help="Check that the API is reachable")
    p_doctor.set_defaults(handler="doctor")

    p_analyze = sub.add_parser("analyze", help="Create an analysis, wait for completion, print result")
    p_analyze.add_argument("company_name", help="Company name or ticker")
    p_analyze.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        metavar="SEC",
        help="Max seconds to wait for a terminal status (default: 600)",
    )
    p_analyze.add_argument(
        "--interval",
        type=float,
        default=2.0,
        metavar="SEC",
        help="Seconds between status polls (default: 2)",
    )
    p_analyze.add_argument(
        "--json",
        action="store_true",
        help="Print full AnalysisOutputsResponse JSON to stdout when terminal",
    )
    p_analyze.add_argument(
        "--show-id",
        action="store_true",
        help="Log analysis_id to stderr when created",
    )
    p_analyze.set_defaults(handler="analyze")

    p_export = sub.add_parser("export", help="Export analysis artifacts (txt, md, json) under output dir")
    p_export.add_argument("analysis_id", help="Analysis UUID from create or --show-id")
    p_export.add_argument(
        "--output-dir",
        default="exports",
        metavar="DIR",
        help="Base directory for exports (default: exports)",
    )
    p_export.set_defaults(handler="export")

    p_tui = sub.add_parser("tui", help="Open the Textual TUI (uses PREIPO_API_URL / PREIPO_WS_URL)")
    p_tui.set_defaults(handler="tui")

    args = parser.parse_args()
    _configure_logging(verbose=args.verbose)
    log = logging.getLogger("preipo")

    api_base = (args.api_url or default_api_base()).rstrip("/")

    if args.handler == "tui" and args.api_url:
        _apply_api_url_to_env(args.api_url)

    if args.handler == "doctor":
        code = _cmd_doctor(api_base, log)
    elif args.handler == "analyze":
        code = _cmd_analyze(
            api_base,
            args.company_name,
            timeout_sec=args.timeout,
            interval_sec=args.interval,
            json_mode=args.json,
            show_id=args.show_id,
            log=log,
        )
    elif args.handler == "export":
        code = _cmd_export(api_base, args.analysis_id, args.output_dir, log)
    elif args.handler == "tui":
        code = _cmd_tui()
    else:
        raise RuntimeError(f"unknown command {args.handler!r}")

    raise SystemExit(code)
