from __future__ import annotations

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
        (_METRIC_LABEL["trough_price"], str(om.trough_price) if om.trough_price is not None else "—"),
        (_METRIC_LABEL["lock_up_cliff_date"], str(om.lock_up_cliff_date) if om.lock_up_cliff_date is not None else "—"),
        (_METRIC_LABEL["price_at_lock_up_cliff"], str(om.price_at_lock_up_cliff) if om.price_at_lock_up_cliff is not None else "—"),
    ]


def render_result_plain(result: SingleAgentResult) -> str:
    lines: list[str] = []
    lines.append(result.company_name)
    lines.append("")

    om = result.outcome_metrics
    if om is not None:
        rows = _outcome_rows(om)
        col_w = max(len(label) for label, _ in rows)
        lines.append("Outcome")
        for label, value in rows:
            lines.append(f"  {label:<{col_w}}  {value}")
        lines.append("")

    if result.narrative is not None:
        n = result.narrative
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
    else:
        if result.patterns:
            lines.append("Patterns")
            for p in result.patterns:
                lines.append(f"- {p.signal} | visible_at_ipo={p.was_visible_at_ipo} | {p.outcome}")
            lines.append("")

        if result.claim_checks:
            lines.append("ClaimChecks")
            for c in result.claim_checks:
                lines.append(f"- {c.claim_id}: {c.status} (confidence={c.confidence})")
                for q in c.evidence_quotes[:3]:
                    lines.append(f"  - {q}")
            lines.append("")

        if result.prediction_claims:
            lines.append("PredictionClaims")
            for c in result.prediction_claims:
                lines.append(f"- {c.claim_id} [{c.claim_type}] {c.prediction_text}")
            lines.append("")

        if result.filing_facts:
            lines.append("FilingFacts")
            for f in result.filing_facts:
                lines.append(f"- {f.fact_id} {f.metric}={f.value} {f.units or ''}".rstrip())
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_result_markdown(result: SingleAgentResult) -> str:
    lines: list[str] = []
    lines.append(f"# {result.company_name}")
    lines.append("")

    om = result.outcome_metrics
    if om is not None:
        lines.append("## Outcome")
        lines.append("")
        lines.append("| metric | value |")
        lines.append("|---|---|")
        for label, value in _outcome_rows(om):
            lines.append(f"| {label} | {value} |")
        lines.append("")

    if result.narrative is not None:
        n = result.narrative
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
    else:
        if result.claim_checks:
            lines.append("## Claim checks")
            lines.append("")
            for c in result.claim_checks:
                lines.append(f"- **{c.claim_id}**: `{c.status}` (confidence `{c.confidence}`)")
                for q in c.evidence_quotes[:5]:
                    lines.append(f"  - {q}")
            lines.append("")

        if result.patterns:
            lines.append("## Patterns")
            lines.append("")
            for p in result.patterns:
                lines.append(f"- **{p.signal}** — visible_at_ipo={p.was_visible_at_ipo} — {p.outcome}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"

