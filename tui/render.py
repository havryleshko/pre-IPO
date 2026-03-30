from __future__ import annotations

from tui.types import SingleAgentResult


def render_result_plain(result: SingleAgentResult) -> str:
    lines: list[str] = []
    lines.append(result.company_name)
    lines.append("")

    om = result.outcome_metrics
    if om is not None:
        lines.append("Outcome")
        lines.append(f"- ipo_price: {om.ipo_price}")
        lines.append(f"- current_price: {om.current_price}")
        lines.append(f"- performance_since_ipo_pct: {om.performance_since_ipo_pct}")
        lines.append(f"- peak_price: {om.peak_price}")
        lines.append(f"- trough_price: {om.trough_price}")
        lines.append(f"- lock_up_cliff_date: {om.lock_up_cliff_date}")
        lines.append(f"- price_at_lock_up_cliff: {om.price_at_lock_up_cliff}")
        lines.append("")

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
        lines.append(f"| ipo_price | {om.ipo_price} |")
        lines.append(f"| current_price | {om.current_price} |")
        lines.append(f"| performance_since_ipo_pct | {om.performance_since_ipo_pct} |")
        lines.append(f"| peak_price | {om.peak_price} |")
        lines.append(f"| trough_price | {om.trough_price} |")
        lines.append(f"| lock_up_cliff_date | {om.lock_up_cliff_date} |")
        lines.append(f"| price_at_lock_up_cliff | {om.price_at_lock_up_cliff} |")
        lines.append("")

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

