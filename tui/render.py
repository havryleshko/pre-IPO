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

_CLAIM_TYPE_LABEL: dict[str, str] = {
    "revenue": "Revenue",
    "ad_revenue": "Ad revenue",
    "growth_rate": "Growth rate",
    "net_loss": "Net loss",
    "valuation": "Valuation",
    "share_count": "Share count",
    "proceeds": "Proceeds",
    "offering_price_range": "Offering price",
    "other": "Other",
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
        derived_rows = _derived_outcome_rows(om)
        if derived_rows:
            dw = max(len(lbl) for lbl, _ in derived_rows)
            for lbl, val in derived_rows:
                lines.append(f"  {lbl:<{dw}}  {val}")
        lines.append("")

    if result.patterns:
        lines.append("Patterns")
        for p in result.patterns[:6]:
            vis = "visible pre-IPO" if p.was_visible_at_ipo else "hindsight"
            lines.append(f"  {p.signal}  [{vis}]  {p.outcome}")
        lines.append("")

    discrepancies = list(result.news_filing_discrepancies or [])
    news_claims = list(result.news_derived_claims or [])
    if discrepancies:
        lines.append("Headlines vs filing")
        for d in discrepancies[:5]:
            ctype = "numeric" if d.contradiction_type == "derived_numeric_contradiction" else "text"
            lines.append(f"  [{ctype}] {d.news_evidence[:80]} vs {d.filing_evidence[:60]}")
        lines.append("")
    elif news_claims:
        lines.append("News claims extracted")
        type_groups: dict[str, list[str]] = {}
        for nc in news_claims[:10]:
            label = _CLAIM_TYPE_LABEL.get(nc.claim_type, nc.claim_type)
            val_str = f" = {nc.normalized_value} {nc.units or ''}".rstrip() if nc.normalized_value is not None else ""
            type_groups.setdefault(label, []).append(f"{nc.evidence_quote[:60]}{val_str}")
        for label, items in type_groups.items():
            lines.append(f"  {label}: {items[0]}")
        lines.append("")

    if result.filing_facts:
        lines.append("Filing snapshot")
        for f in result.filing_facts[:8]:
            val_str = f"{f.value} {f.units or ''}".rstrip() if f.value is not None else "—"
            lines.append(f"  {f.metric:<30}  {val_str}")
        lines.append("")

    if result.claim_checks:
        lines.append("S-1 claim checks")
        for c in result.claim_checks[:6]:
            status_icon = {"supported": "+", "missed": "!", "mixed": "~", "unverifiable": "?"}.get(c.status, "?")
            lines.append(f"  [{status_icon}] {c.claim_id} — {c.status} (confidence={c.confidence})")
            for q in c.evidence_quotes[:2]:
                lines.append(f"      {q[:90]}")
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
        lines.append("S-1 projections")
        for c in result.prediction_claims[:6]:
            lines.append(f"  [{c.claim_type}] {c.prediction_text[:100]}")
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
        for lbl, val in _derived_outcome_rows(om):
            lines.append(f"| {lbl} | {val} |")
        lines.append("")

    if result.patterns:
        lines.append("## Patterns")
        lines.append("")
        for p in result.patterns[:6]:
            vis = "visible pre-IPO" if p.was_visible_at_ipo else "hindsight"
            lines.append(f"- **{p.signal}** ({vis}) — {p.outcome}")
        lines.append("")

    discrepancies = list(result.news_filing_discrepancies or [])
    news_claims = list(result.news_derived_claims or [])
    if discrepancies:
        lines.append("## Headlines vs filing")
        lines.append("")
        for d in discrepancies[:5]:
            ctype = "numeric" if d.contradiction_type == "derived_numeric_contradiction" else "text"
            lines.append(f"- `[{ctype}]` {d.news_evidence[:120]} — filing: _{d.filing_evidence[:80]}_")
        lines.append("")
    elif news_claims:
        lines.append("## News claims extracted")
        lines.append("")
        for nc in news_claims[:10]:
            label = _CLAIM_TYPE_LABEL.get(nc.claim_type, nc.claim_type)
            val_str = f" = {nc.normalized_value} {nc.units or ''}".rstrip() if nc.normalized_value is not None else ""
            lines.append(f"- **{label}**{val_str}: {nc.evidence_quote[:100]}")
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

    if result.claim_checks:
        lines.append("## S-1 claim checks")
        lines.append("")
        for c in result.claim_checks[:6]:
            lines.append(f"- **{c.claim_id}**: `{c.status}` (confidence `{c.confidence}`)")
            for q in c.evidence_quotes[:2]:
                lines.append(f"  - {q[:120]}")
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
        lines.append("## S-1 projections")
        lines.append("")
        for c in result.prediction_claims[:6]:
            lines.append(f"- `[{c.claim_type}]` {c.prediction_text[:120]}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
