from __future__ import annotations

from io import StringIO

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from tui.types import OutcomeMetrics, SingleAgentResult

_METRIC_LABEL: dict[str, str] = {
    "ipo_price": "IPO price",
    "current_price": "Current price",
    "performance_since_ipo_pct": "Performance since IPO (%)",
    "peak_price": "Peak price",
    "trough_price": "Trough price",
    "lock_up_cliff_date": "Lock-up cliff date",
    "price_at_lock_up_cliff": "Price at lock-up cliff",
}


def _outcome_rows(om: OutcomeMetrics) -> list[tuple[str, str]]:
    return [
        (_METRIC_LABEL["ipo_price"], str(om.ipo_price) if om.ipo_price is not None else "—"),
        (_METRIC_LABEL["current_price"], str(om.current_price) if om.current_price is not None else "—"),
        (_METRIC_LABEL["performance_since_ipo_pct"], str(om.performance_since_ipo_pct) if om.performance_since_ipo_pct is not None else "—"),
        (_METRIC_LABEL["peak_price"], str(om.peak_price) if om.peak_price is not None else "—"),
        ("Peak date", str(om.peak_date) if om.peak_date is not None else "—"),
        (_METRIC_LABEL["trough_price"], str(om.trough_price) if om.trough_price is not None else "—"),
        ("Trough date", str(om.trough_date) if om.trough_date is not None else "—"),
        (_METRIC_LABEL["lock_up_cliff_date"], str(om.lock_up_cliff_date) if om.lock_up_cliff_date is not None else "—"),
        (_METRIC_LABEL["price_at_lock_up_cliff"], str(om.price_at_lock_up_cliff) if om.price_at_lock_up_cliff is not None else "—"),
        ("Recovered to IPO date", str(om.recovered_to_ipo_date) if om.recovered_to_ipo_date is not None else "—"),
        ("Recovered to peak date", str(om.recovered_to_peak_date) if om.recovered_to_peak_date is not None else "—"),
    ]


def _derived_outcome_rows(om: OutcomeMetrics) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if om.ipo_price and om.ipo_price > 0:
        if om.peak_price is not None:
            peak_multiple = om.peak_price / om.ipo_price
            rows.append(("Peak multiple vs IPO", f"{peak_multiple:.2f}x"))
        if om.trough_price is not None:
            trough_pct = (om.trough_price - om.ipo_price) / om.ipo_price * 100.0
            rows.append(("Trough vs IPO price", f"{trough_pct:+.1f}%"))
        if om.peak_price is not None and om.current_price is not None:
            drawdown = (om.current_price - om.peak_price) / om.peak_price * 100.0
            rows.append(("Current vs peak", f"{drawdown:+.1f}%"))
    return rows


def _mandatory_completeness(result: SingleAgentResult) -> str:
    row = result.reference_table_row
    if row is None:
        return "0/7"
    fields = (
        row.company_ticker,
        row.industry_region,
        row.ipo_date,
        row.key_pre_ipo_claims,
        row.long_term_outcome,
        row.forecast_error,
        row.predicted_pattern,
    )
    present = sum(1 for value in fields if str(value).strip() and str(value).strip().lower() != "unavailable")
    return f"{present}/7"


def _delivery_direction(result: SingleAgentResult) -> str:
    forecast_error = result.realized_outcome.forecast_error if result.realized_outcome is not None else ""
    lower = forecast_error.lower()
    if "underdelivered" in lower:
        return "negative"
    if "aligned" in lower:
        return "positive"
    if "mixed" in lower:
        return "mixed"
    return "—"


def _status_color(status: str) -> str:
    mapping = {
        "supported": "green",
        "missed": "red",
        "mixed": "yellow",
        "unverifiable": "cyan",
    }
    return mapping.get(status, "white")


def _claim_check_signal(status: str) -> str:
    mapping = {
        "supported": "Yes",
        "missed": "No",
        "mixed": "Partial",
        "unverifiable": "Unknown",
    }
    return mapping.get(status, "Unknown")


def _pct_color(value: str) -> str:
    if value.startswith("+"):
        return "green"
    if value.startswith("-"):
        return "red"
    return "white"


def _append_reference_row_plain(lines: list[str], result: SingleAgentResult) -> None:
    row = result.reference_table_row
    if row is None:
        return
    lines.append("Reference table row")
    ref_rows = [
        ("Company (Ticker)", row.company_ticker),
        ("Industry / Region", row.industry_region),
        ("IPO Date", row.ipo_date),
        ("Key Pre-IPO Claim(s)", row.key_pre_ipo_claims),
        ("Long-term Outcome (IPO to Apr 2026)", row.long_term_outcome),
        ("Forecast Error", row.forecast_error),
        ("Predicted Pattern (pre-IPO basis)", row.predicted_pattern),
    ]
    col_w = max(len(label) for label, _ in ref_rows)
    for label, value in ref_rows:
        lines.append(f"  {label:<{col_w}}  {value}")
    lines.append("")


def render_result_plain(result: SingleAgentResult) -> str:
    lines: list[str] = []
    lines.append(result.company_name)
    lines.append("")
    _append_reference_row_plain(lines, result)

    om = result.outcome_metrics
    if om is not None:
        rows = _outcome_rows(om)
        col_w = max(len(label) for label, _ in rows)
        lines.append("Outcome")
        for label, value in rows:
            lines.append(f"  {label:<{col_w}}  {value}")
        derived_rows = _derived_outcome_rows(om)
        if derived_rows:
            dw = max(len(lbl) for lbl, _ in derived_rows)
            for lbl, val in derived_rows:
                lines.append(f"  {lbl:<{dw}}  {val}")
        lines.append("")

    if result.claim_checks:
        lines.append("S-1 claim checks")
        for c in result.claim_checks:
            status_icon = {"supported": "+", "missed": "!", "mixed": "~", "unverifiable": "?"}.get(c.status, "?")
            lines.append(f"  [{status_icon}] {c.claim_id} — {_claim_check_signal(c.status)}")
            if c.evidence_quotes:
                lines.append(f"      {c.evidence_quotes[0][:120]}")
            elif c.rationale:
                lines.append(f"      {c.rationale[:120]}")
        lines.append("")

    if result.patterns:
        lines.append("Patterns")
        for p in result.patterns[:6]:
            vis = "visible pre-IPO" if p.was_visible_at_ipo else "hindsight"
            lines.append(f"  {p.signal}  [{vis}]  {p.outcome}")
        lines.append("")

    discrepancies = list(result.news_filing_discrepancies or [])
    if discrepancies:
        lines.append("Headlines vs filing")
        for d in discrepancies[:5]:
            ctype = "numeric" if d.contradiction_type == "derived_numeric_contradiction" else "text"
            lines.append(f"  [{ctype}] {d.news_evidence[:80]} vs {d.filing_evidence[:60]}")
        lines.append("")

    if result.filing_facts:
        lines.append("Filing snapshot")
        for f in result.filing_facts[:8]:
            val_str = f"{f.value} {f.units or ''}".rstrip() if f.value is not None else "—"
            lines.append(f"  {f.metric:<30}  {val_str}")
        lines.append("")

    if result.narrative is not None:
        n = result.narrative
        lines.append("— Interpretation (model-generated) —")
        lines.append(n.headline)
        lines.append("")
        lines.append("Pre-IPO story")
        for item in n.pre_ipo_story:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("Post-IPO grounding")
        for item in n.post_ipo_grounding:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("Key differences")
        for item in n.key_differences:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("What to watch")
        for item in n.watch_items:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("Sources")
        for item in n.sources_cited:
            lines.append(f"- {item}")
        lines.append("")

    if result.prediction_claims:
        lines.append("Pre-IPO claims")
        for c in result.prediction_claims[:6]:
            lines.append(f"  [{c.claim_type}] {c.prediction_text[:100]}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_result_cli(result: SingleAgentResult) -> str:
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, color_system=None, width=120)

    title = result.reference_table_row.company_ticker if result.reference_table_row is not None else result.company_name
    header = Panel.fit(title, title="preipo analyze", box=box.ROUNDED)
    console.print(header)
    summary = Table(box=box.SIMPLE_HEAVY, show_header=True)
    summary.add_column("Pattern id", style="bold")
    summary.add_column("Source")
    summary.add_column("Mandatory fields")
    summary.add_column("Delivery direction")
    summary.add_row(
        str(result.pattern_classification.primary_pattern_id)
        if result.pattern_classification and result.pattern_classification.primary_pattern_id
        else "—",
        result.pattern_classification.source if result.pattern_classification else "—",
        _mandatory_completeness(result),
        _delivery_direction(result),
    )
    console.print(Panel(summary, title="Summary", box=box.ROUNDED))

    row = result.reference_table_row
    if row is not None:
        ref_table = Table(box=box.SIMPLE_HEAVY, show_header=True)
        ref_table.add_column("Field", style="bold")
        ref_table.add_column("Value", overflow="fold")
        ref_table.add_row("Company (Ticker)", row.company_ticker)
        ref_table.add_row("Industry / Region", row.industry_region)
        ref_table.add_row("IPO Date", row.ipo_date)
        ref_table.add_row("Key Pre-IPO Claim(s)", row.key_pre_ipo_claims)
        ref_table.add_row("Long-term Outcome (IPO to Apr 2026)", row.long_term_outcome)
        ref_table.add_row("Forecast Error", row.forecast_error)
        ref_table.add_row("Predicted Pattern (pre-IPO basis)", row.predicted_pattern)
        console.print(Panel(ref_table, title="Reference table row", box=box.ROUNDED))

    if result.outcome_metrics is not None:
        outcome_table = Table(box=box.SIMPLE_HEAVY, show_header=True)
        outcome_table.add_column("Outcome field", style="bold")
        outcome_table.add_column("Value")
        for label, value in _outcome_rows(result.outcome_metrics):
            style = _pct_color(value) if "%" in value or value.startswith(("+", "-")) else "white"
            outcome_table.add_row(label, Text(value, style=style))
        for label, value in _derived_outcome_rows(result.outcome_metrics):
            outcome_table.add_row(label, Text(value, style=_pct_color(value)))
        console.print(Panel(outcome_table, title="Outcome", box=box.ROUNDED))

    if result.claim_checks:
        checks = Table(box=box.SIMPLE_HEAVY, show_header=True)
        checks.add_column("Check")
        checks.add_column("Signal")
        checks.add_column("Evidence")
        for check in result.claim_checks:
            evidence = check.evidence_quotes[0] if check.evidence_quotes else (check.rationale or "—")
            checks.add_row(
                check.claim_id,
                Text(_claim_check_signal(check.status), style=_status_color(check.status)),
                evidence[:120],
            )
        console.print(Panel(checks, title="S-1 claim checks", box=box.ROUNDED))

    if result.patterns:
        patterns = Table(box=box.SIMPLE_HEAVY, show_header=True)
        patterns.add_column("Signal")
        patterns.add_column("Visibility")
        patterns.add_column("Outcome")
        for item in result.patterns[:6]:
            patterns.add_row(item.signal, "visible pre-IPO" if item.was_visible_at_ipo else "hindsight", item.outcome)
        console.print(Panel(patterns, title="Patterns", box=box.ROUNDED))

    discrepancies = list(result.news_filing_discrepancies or [])
    if discrepancies:
        disc = Table(box=box.SIMPLE_HEAVY, show_header=True)
        disc.add_column("Type")
        disc.add_column("News evidence")
        disc.add_column("Filing evidence")
        for item in discrepancies[:5]:
            dtype = "numeric" if item.contradiction_type == "derived_numeric_contradiction" else "text"
            disc.add_row(dtype, item.news_evidence[:120], item.filing_evidence[:120])
        console.print(Panel(disc, title="Headlines vs filing", box=box.ROUNDED))

    return buf.getvalue()


def render_result_markdown(result: SingleAgentResult) -> str:
    lines: list[str] = []
    lines.append(f"# {result.company_name}")
    lines.append("")

    if result.reference_table_row is not None:
        row = result.reference_table_row
        lines.append("## Reference table row")
        lines.append("")
        lines.append("| field | value |")
        lines.append("|---|---|")
        lines.append(f"| Company (Ticker) | {row.company_ticker} |")
        lines.append(f"| Industry / Region | {row.industry_region} |")
        lines.append(f"| IPO Date | {row.ipo_date} |")
        lines.append(f"| Key Pre-IPO Claim(s) | {row.key_pre_ipo_claims} |")
        lines.append(f"| Long-term Outcome (IPO to Apr 2026) | {row.long_term_outcome} |")
        lines.append(f"| Forecast Error | {row.forecast_error} |")
        lines.append(f"| Predicted Pattern (pre-IPO basis) | {row.predicted_pattern} |")
        lines.append("")

    om = result.outcome_metrics
    if om is not None:
        lines.append("## Outcome")
        lines.append("")
        lines.append("| metric | value |")
        lines.append("|---|---|")
        for label, value in _outcome_rows(om):
            lines.append(f"| {label} | {value} |")
        for lbl, val in _derived_outcome_rows(om):
            lines.append(f"| {lbl} | {val} |")
        lines.append("")

    if result.claim_checks:
        lines.append("## S-1 claim checks")
        lines.append("")
        for c in result.claim_checks:
            lines.append(f"- **{c.claim_id}**: `{_claim_check_signal(c.status)}`")
            if c.evidence_quotes:
                lines.append(f"  - {c.evidence_quotes[0][:120]}")
            elif c.rationale:
                lines.append(f"  - {c.rationale[:120]}")
        lines.append("")

    if result.patterns:
        lines.append("## Patterns")
        lines.append("")
        for p in result.patterns[:6]:
            vis = "visible pre-IPO" if p.was_visible_at_ipo else "hindsight"
            lines.append(f"- **{p.signal}** ({vis}) — {p.outcome}")
        lines.append("")

    discrepancies = list(result.news_filing_discrepancies or [])
    if discrepancies:
        lines.append("## Headlines vs filing")
        lines.append("")
        for d in discrepancies[:5]:
            ctype = "numeric" if d.contradiction_type == "derived_numeric_contradiction" else "text"
            lines.append(f"- `[{ctype}]` {d.news_evidence[:120]} — filing: _{d.filing_evidence[:80]}_")
        lines.append("")

    if result.filing_facts:
        lines.append("## Filing snapshot")
        lines.append("")
        lines.append("| metric | value | units |")
        lines.append("|---|---|---|")
        for f in result.filing_facts[:8]:
            val = str(f.value) if f.value is not None else "—"
            lines.append(f"| {f.metric} | {val} | {f.units or '—'} |")
        lines.append("")

    if result.narrative is not None:
        n = result.narrative
        lines.append("---")
        lines.append("")
        lines.append(f"> {n.headline}")
        lines.append("")
        lines.append("## Pre-IPO story")
        lines.append("")
        for item in n.pre_ipo_story:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## Post-IPO grounding")
        lines.append("")
        for item in n.post_ipo_grounding:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## Key differences")
        lines.append("")
        for item in n.key_differences:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## What to watch")
        lines.append("")
        for item in n.watch_items:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## Sources")
        lines.append("")
        for item in n.sources_cited:
            lines.append(f"- {item}")
        lines.append("")

    if result.prediction_claims:
        lines.append("## Pre-IPO claims")
        lines.append("")
        for c in result.prediction_claims[:6]:
            lines.append(f"- `[{c.claim_type}]` {c.prediction_text[:120]}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
