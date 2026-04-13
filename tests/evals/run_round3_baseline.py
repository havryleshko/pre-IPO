from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cli.http_client import PreipoHttpClient, default_api_base
from tests.evals.reference_output_scoring import _has_text, score_reference_outputs
from tests.evals.round2_cohorts import ROUND3_MANDATORY_GATE_COHORT
from tui.types import AnalysisOutputsResponse, SingleAgentResult

from backend.services.reference_output_contract import lookup_reference_record

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

COHORTS: dict[str, tuple[str, ...]] = {
    "round3_mandatory_gate_12": ROUND3_MANDATORY_GATE_COHORT,
}


@dataclass
class CompanyCohortRow:
    cohort: str
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
    pattern_id: int | None
    reference_company_ticker: str | None


def _git_sha() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True)
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


def _bucket_for_result(result: SingleAgentResult | None) -> str:
    if result is None or result.pattern_classification is None:
        return "unavailable"
    return "reference_exact" if result.pattern_classification.source == "reference_exact" else "heuristic"


def _industry_region_source(result: SingleAgentResult | None) -> str:
    if result is None or result.reference_table_row is None:
        return "unavailable"
    if result.pattern_classification and result.pattern_classification.source == "reference_exact":
        return "csv"
    return "yahoo_info" if _has_text(result.reference_table_row.industry_region) else "unavailable"


def _reference_record_for_result(result: SingleAgentResult | None, company_input: str):
    if result is None:
        return None
    ticker = result.company_profile.ticker if result.company_profile else None
    company_name = result.company_name or company_input
    return lookup_reference_record(company_name=company_name, ticker=ticker)


def _company_row(
    cohort: str,
    data: AnalysisOutputsResponse,
    company_input: str,
) -> tuple[CompanyCohortRow, SingleAgentResult | None, Any]:
    result = data.analysis_result
    mandatory_present, mandatory_total, missing_fields = _mandatory_presence(result)
    reference_record = _reference_record_for_result(result, company_input)
    row = CompanyCohortRow(
        cohort=cohort,
        input_company=company_input,
        analysis_id=data.analysis_id,
        status=data.status,
        company_name=data.company_name,
        resolved_ticker=(result.company_profile.ticker if result and result.company_profile else None),
        bucket=_bucket_for_result(result),
        row_source=("csv" if _bucket_for_result(result) == "reference_exact" else "heuristic"),
        industry_region_source=_industry_region_source(result),
        mandatory_present=mandatory_present,
        mandatory_total=mandatory_total,
        missing_fields=missing_fields,
        predicted_pattern=(result.reference_table_row.predicted_pattern if result and result.reference_table_row else None),
        pattern_id=(result.pattern_classification.primary_pattern_id if result and result.pattern_classification else None),
        reference_company_ticker=(reference_record.company_ticker if reference_record else None),
    )
    return row, result, reference_record


def _cohort_summary(rows: list[CompanyCohortRow], reference_metrics: dict[str, Any] | None) -> dict[str, Any]:
    completed = sum(1 for row in rows if row.status in {"completed", "completed_with_flags"})
    reference_exact = sum(1 for row in rows if row.bucket == "reference_exact")
    heuristic = sum(1 for row in rows if row.bucket == "heuristic")
    mandatory_total = sum(row.mandatory_total for row in rows)
    mandatory_present = sum(row.mandatory_present for row in rows)
    missing = Counter(field for row in rows for field in row.missing_fields)
    patterns = Counter(row.predicted_pattern for row in rows if row.predicted_pattern)
    return {
        "total_inputs": len(rows),
        "completed": completed,
        "reference_exact": reference_exact,
        "heuristic": heuristic,
        "mandatory_field_coverage": (mandatory_present / mandatory_total) if mandatory_total else 0.0,
        "missing_field_distribution": dict(sorted(missing.items())),
        "pattern_distribution": dict(sorted(patterns.items())),
        "reference_metrics": reference_metrics,
    }


def _markdown_report(
    *,
    api_base: str,
    git_sha: str,
    rows_by_cohort: dict[str, list[CompanyCohortRow]],
    summaries: dict[str, dict[str, Any]],
) -> str:
    lines = [
        "# Round 3 eval baseline",
        "",
        f"- Generated at: `{datetime.now(timezone.utc).isoformat()}`",
        f"- Git SHA: `{git_sha}`",
        f"- API base: `{api_base}`",
        "",
    ]
    for cohort_name, cohort_rows in rows_by_cohort.items():
        summary = summaries[cohort_name]
        lines.append(f"## Cohort: `{cohort_name}`")
        lines.append("")
        lines.append(f"- Inputs: `{', '.join(COHORTS[cohort_name])}`")
        lines.append(f"- Completed analyses: `{summary['completed']}/{summary['total_inputs']}`")
        lines.append(f"- `reference_exact`: `{summary['reference_exact']}`")
        lines.append(f"- `heuristic`: `{summary['heuristic']}`")
        lines.append(f"- mandatory_field_coverage: `{summary['mandatory_field_coverage']:.4f}`")
        lines.append(f"- missing_field_distribution: `{summary['missing_field_distribution']}`")
        lines.append(f"- pattern_distribution: `{summary['pattern_distribution']}`")
        ref_metrics = summary["reference_metrics"]
        if ref_metrics is None:
            lines.append("- canonical_reference_metrics: `not_applicable`")
        else:
            lines.append("- canonical_reference_metrics:")
            lines.append(f"  - mandatory_field_coverage: `{ref_metrics['mandatory_field_coverage']:.4f}`")
            lines.append(f"  - pattern_accuracy: `{ref_metrics['pattern_accuracy']:.4f}`")
            lines.append(
                f"  - failing_company_ids: `{', '.join(ref_metrics['failing_company_ids']) if ref_metrics['failing_company_ids'] else '-'}`"
            )
        lines.extend(
            [
                "",
                "| Input | Analysis ID | Status | Resolved ticker | Bucket | Mandatory | Missing fields | Pattern | Reference row |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in cohort_rows:
            lines.append(
                f"| `{row.input_company}` | `{row.analysis_id}` | `{row.status}` | `{row.resolved_ticker or '-'}` | "
                f"`{row.bucket}` | `{row.mandatory_present}/{row.mandatory_total}` | "
                f"`{', '.join(row.missing_fields) if row.missing_fields else '-'}` | `{row.predicted_pattern or '-'}` | `{row.reference_company_ticker or '-'}` |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=default_api_base())
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--output-json", default="tests/evals/round3_baseline.json")
    parser.add_argument("--output-md", default="tests/evals/round3_baseline.md")
    args = parser.parse_args()

    api_base = args.api_url.rstrip("/")
    json_path = Path(args.output_json)
    md_path = Path(args.output_md)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    rows_by_cohort: dict[str, list[CompanyCohortRow]] = {name: [] for name in COHORTS}
    summaries: dict[str, dict[str, Any]] = {}

    with PreipoHttpClient(api_base=api_base, timeout=max(60.0, args.interval + 10.0)) as http:
        http.fetch_openapi()
        for cohort_name, companies in COHORTS.items():
            predictions: dict[str, SingleAgentResult] = {}
            expected_rows: list[Any] = []
            for company in companies:
                created = http.create_analysis(company)
                data = _poll_until_terminal(
                    http,
                    created.analysis_id,
                    timeout_sec=args.timeout,
                    interval_sec=args.interval,
                )
                row, result, reference_record = _company_row(cohort_name, data, company)
                rows_by_cohort[cohort_name].append(row)
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
            summaries[cohort_name] = _cohort_summary(rows_by_cohort[cohort_name], reference_metrics)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "api_base": api_base,
        "cohorts": {name: list(companies) for name, companies in COHORTS.items()},
        "rows_by_cohort": {name: [asdict(row) for row in rows] for name, rows in rows_by_cohort.items()},
        "summaries": summaries,
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        _markdown_report(
            api_base=api_base,
            git_sha=payload["git_sha"],
            rows_by_cohort=rows_by_cohort,
            summaries=summaries,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
