from __future__ import annotations

import argparse
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cli.http_client import PreipoHttpClient, default_api_base
from tests.evals.reference_output_scoring import _has_text, score_reference_outputs
from tui.types import AnalysisOutputsResponse, SingleAgentResult

from backend.services.reference_output_contract import lookup_reference_record

COMPANIES = ("RKLB", "PL", "IONS", "COHR", "IOVA", "QBTS", "MP", "ISRG", "LHX")
TERMINAL_STATUSES = frozenset({"failed", "completed", "completed_with_flags"})
MANDATORY_FIELDS = (
    "company_ticker",
    "industry_region",
    "ipo_date",
    "key_pre_ipo_claims",
    "long_term_outcome",
    "forecast_error",
    "predicted_pattern",
)


@dataclass
class CompanyBaselineRow:
    input_company: str
    analysis_id: str
    status: str
    company_name: str
    resolved_ticker: str | None
    bucket: str
    row_source: str
    industry_region_source: str
    mandatory_present: int
    mandatory_total: int
    missing_fields: list[str]
    predicted_pattern: str | None
    reference_company_ticker: str | None


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _poll_until_terminal(
    http: PreipoHttpClient,
    analysis_id: str,
    *,
    timeout_sec: float,
    interval_sec: float,
) -> AnalysisOutputsResponse:
    deadline = time.monotonic() + timeout_sec
    data = http.get_analysis(analysis_id)
    while data.status not in TERMINAL_STATUSES:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out for analysis_id={analysis_id} status={data.status}")
        time.sleep(interval_sec)
        data = http.get_analysis(analysis_id)
    return data


def _mandatory_presence(result: SingleAgentResult | None) -> tuple[int, int, list[str]]:
    if result is None or result.reference_table_row is None:
        return 0, len(MANDATORY_FIELDS), list(MANDATORY_FIELDS)
    present = 0
    missing_fields: list[str] = []
    row = result.reference_table_row
    for field_name in MANDATORY_FIELDS:
        if _has_text(getattr(row, field_name, None)):
            present += 1
        else:
            missing_fields.append(field_name)
    return present, len(MANDATORY_FIELDS), missing_fields


def _industry_region_source(result: SingleAgentResult | None) -> str:
    if result is None or result.reference_table_row is None:
        return "unavailable"
    if result.pattern_classification and result.pattern_classification.source == "reference_exact":
        return "csv"
    industry_region = result.reference_table_row.industry_region
    if not _has_text(industry_region):
        return "unavailable"
    return "yahoo_info"


def _bucket_for_result(result: SingleAgentResult | None) -> str:
    if result is None or result.pattern_classification is None:
        return "unavailable"
    source = result.pattern_classification.source
    if source == "reference_exact":
        return "reference_exact"
    return "heuristic"


def _row_source_for_result(result: SingleAgentResult | None) -> str:
    if result is None or result.pattern_classification is None:
        return "unavailable"
    return "csv" if result.pattern_classification.source == "reference_exact" else "heuristic"


def _reference_record_for_result(result: SingleAgentResult | None, company_input: str):
    if result is None:
        return None
    ticker = result.company_profile.ticker if result.company_profile else None
    company_name = result.company_name or company_input
    return lookup_reference_record(company_name=company_name, ticker=ticker)


def _company_row(data: AnalysisOutputsResponse, company_input: str) -> tuple[CompanyBaselineRow, SingleAgentResult | None, Any]:
    result = data.analysis_result
    mandatory_present, mandatory_total, missing_fields = _mandatory_presence(result)
    reference_record = _reference_record_for_result(result, company_input)
    resolved_ticker = result.company_profile.ticker if result and result.company_profile else None
    predicted_pattern = result.reference_table_row.predicted_pattern if result and result.reference_table_row else None
    row = CompanyBaselineRow(
        input_company=company_input,
        analysis_id=data.analysis_id,
        status=data.status,
        company_name=data.company_name,
        resolved_ticker=resolved_ticker,
        bucket=_bucket_for_result(result),
        row_source=_row_source_for_result(result),
        industry_region_source=_industry_region_source(result),
        mandatory_present=mandatory_present,
        mandatory_total=mandatory_total,
        missing_fields=missing_fields,
        predicted_pattern=predicted_pattern,
        reference_company_ticker=reference_record.company_ticker if reference_record else None,
    )
    return row, result, reference_record


def _markdown_report(
    *,
    api_base: str,
    git_sha: str,
    rows: list[CompanyBaselineRow],
    reference_metrics: dict[str, Any] | None,
) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Round 1 reference baseline",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Git SHA: `{git_sha}`",
        f"- API base: `{api_base}`",
        f"- Inputs: `{', '.join(COMPANIES)}`",
        "",
        "## Per-company",
        "",
        "| Input | Analysis ID | Status | Resolved ticker | Bucket | Row source | Industry/Region source | Mandatory fields | Missing fields | Pattern | Reference row |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| `{row.input_company}` | `{row.analysis_id}` | `{row.status}` | "
            f"`{row.resolved_ticker or '-'}` | `{row.bucket}` | `{row.row_source}` | "
            f"`{row.industry_region_source}` | `{row.mandatory_present}/{row.mandatory_total}` | "
            f"`{', '.join(row.missing_fields) if row.missing_fields else '-'}` | "
            f"`{row.predicted_pattern or '-'}` | `{row.reference_company_ticker or '-'}` |"
        )
    lines.extend(["", "## Aggregate", ""])
    reference_exact = sum(1 for row in rows if row.bucket == "reference_exact")
    heuristic = sum(1 for row in rows if row.bucket == "heuristic")
    completed = sum(1 for row in rows if row.status in {"completed", "completed_with_flags"})
    lines.append(f"- Completed analyses: `{completed}/{len(rows)}`")
    lines.append(f"- `reference_exact`: `{reference_exact}`")
    lines.append(f"- `heuristic`: `{heuristic}`")
    if reference_metrics is None:
        lines.append("- ReferenceOutputMetrics: `not_applicable` (no inputs matched canonical reference rows)")
    else:
        lines.append(f"- mandatory_field_coverage: `{reference_metrics['mandatory_field_coverage']:.4f}`")
        lines.append(f"- pattern_accuracy: `{reference_metrics['pattern_accuracy']:.4f}`")
        lines.append(
            f"- failing_company_ids: `{', '.join(reference_metrics['failing_company_ids']) if reference_metrics['failing_company_ids'] else '-'}`"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=default_api_base())
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument(
        "--output-json",
        default="tests/evals/round1_reference_baseline.json",
    )
    parser.add_argument(
        "--output-md",
        default="tests/evals/round1_reference_baseline.md",
    )
    args = parser.parse_args()

    api_base = args.api_url.rstrip("/")
    json_path = Path(args.output_json)
    md_path = Path(args.output_md)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[CompanyBaselineRow] = []
    predictions: dict[str, SingleAgentResult] = {}
    expected_rows: list[Any] = []

    with PreipoHttpClient(api_base=api_base, timeout=max(60.0, args.interval + 10.0)) as http:
        http.fetch_openapi()
        for company in COMPANIES:
            created = http.create_analysis(company)
            data = _poll_until_terminal(
                http,
                created.analysis_id,
                timeout_sec=args.timeout,
                interval_sec=args.interval,
            )
            row, result, reference_record = _company_row(data, company)
            rows.append(row)
            if result is not None and row.status in {"completed", "completed_with_flags"}:
                predictions[company] = result
            if reference_record is not None:
                expected_rows.append(reference_record)

    reference_metrics = None
    if expected_rows:
        metrics = score_reference_outputs(expected_rows, predictions)
        reference_metrics = {
            "mandatory_field_coverage": metrics.mandatory_field_coverage,
            "pattern_accuracy": metrics.pattern_accuracy,
            "failing_company_ids": metrics.failing_company_ids,
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "api_base": api_base,
        "companies": list(COMPANIES),
        "rows": [asdict(row) for row in rows],
        "reference_metrics": reference_metrics,
    }
    json_path.write_text(__import__("json").dumps(payload, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        _markdown_report(
            api_base=api_base,
            git_sha=payload["git_sha"],
            rows=rows,
            reference_metrics=reference_metrics,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
