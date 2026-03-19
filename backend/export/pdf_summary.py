import io
import logging
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)


def _fmt(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val:,.2f}" if abs(val) >= 1 else str(val)


def _fmt_pct(val: float) -> str:
    return f"{val:.0f}%"


def _get(d: dict[str, Any] | None, *keys: str, default: Any = None) -> Any:
    if d is None:
        return default
    for k in keys:
        d = d.get(k) if isinstance(d, dict) else None
        if d is None:
            return default
    return d


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def generate_summary_pdf(record: dict[str, Any]) -> bytes:
    company_name = record.get("company_name") or "IPO Analysis"
    created_at = record.get("created_at")
    analysis_date = created_at.strftime("%Y-%m-%d") if isinstance(created_at, datetime) else "—"
    scenario_data = record.get("scenario_output") or {}
    rec_data = record.get("recommendation_output") or {}
    harvester_data = record.get("harvester_output") or {}

    scenarios = _get(scenario_data, "scenarios") or {}
    recommendations = _get(rec_data, "recommendations") or {}
    sources_active = _get(harvester_data, "sources_active") or []
    harvested_at = _get(harvester_data, "harvested_at")
    if isinstance(harvested_at, datetime):
        sources_ts = harvested_at.strftime("%Y-%m-%d %H:%M UTC")
    else:
        sources_ts = "—"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=6,
    )
    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=10,
        spaceAfter=4,
    )
    body_style = styles["Normal"]

    story = []
    story.append(Paragraph(_escape(str(company_name)), title_style))
    story.append(Paragraph(_escape(f"Analysis date: {analysis_date}"), body_style))
    story.append(Spacer(1, 0.2 * inch))

    pess = scenarios.get("pessimistic") or {}
    real = scenarios.get("realistic") or {}
    opt = scenarios.get("optimistic") or {}

    pt_pess = _get(pess, "price_targets") or {}
    pt_real = _get(real, "price_targets") or {}
    pt_opt = _get(opt, "price_targets") or {}

    table_data = [
        ["", "30d", "90d", "1yr", "Positioning", "Risk warning"],
        [
            f"Pessimistic ({_fmt_pct(pess.get('probability', 0))}%)",
            _fmt(pt_pess.get("30_days")),
            _fmt(pt_pess.get("90_days")),
            _fmt(pt_pess.get("1_year")),
            _get(recommendations, "pessimistic", "recommended_positioning") or "—",
            _get(recommendations, "pessimistic", "risk_warning") or "—",
        ],
        [
            f"Realistic ({_fmt_pct(real.get('probability', 0))}%)",
            _fmt(pt_real.get("30_days")),
            _fmt(pt_real.get("90_days")),
            _fmt(pt_real.get("1_year")),
            _get(recommendations, "realistic", "recommended_positioning") or "—",
            _get(recommendations, "realistic", "risk_warning") or "—",
        ],
        [
            f"Optimistic ({_fmt_pct(opt.get('probability', 0))}%)",
            _fmt(pt_opt.get("30_days")),
            _fmt(pt_opt.get("90_days")),
            _fmt(pt_opt.get("1_year")),
            _get(recommendations, "optimistic", "recommended_positioning") or "—",
            _get(recommendations, "optimistic", "risk_warning") or "—",
        ],
    ]
    t = Table(table_data, colWidths=[1.2 * inch, 0.6 * inch, 0.6 * inch, 0.6 * inch, 1.8 * inch, 1.8 * inch])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F7F2E9")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 0.2 * inch))

    retail_summary = rec_data.get("retail_summary")
    if isinstance(retail_summary, dict):
        def _render_list(title: str, items: list[Any]) -> None:
            if not items:
                return
            story.append(Spacer(1, 0.1 * inch))
            story.append(Paragraph(title, heading_style))
            bullets = "<br/>".join(_escape(f"- {str(item)}") for item in items[:12] if item is not None)
            if bullets:
                story.append(Paragraph(bullets, body_style))

        action_ideas = retail_summary.get("action_ideas") or {}
        conservative = action_ideas.get("conservative") if isinstance(action_ideas, dict) else None
        tactical = action_ideas.get("tactical") if isinstance(action_ideas, dict) else None
        risk_control = action_ideas.get("risk_control") if isinstance(action_ideas, dict) else None

        story.append(Paragraph("Simple Investor View", heading_style))
        verdict_line = retail_summary.get("verdict_line") or "—"
        story.append(Paragraph(_escape(str(verdict_line)), body_style))

        what_i_see_now = retail_summary.get("what_i_see_now") or []
        why_that_matters = retail_summary.get("why_that_matters") or []
        the_good = retail_summary.get("the_good") or []
        the_risk = retail_summary.get("the_risk") or []
        key_data_points = retail_summary.get("key_data_points") or []

        _render_list("What I See Now", what_i_see_now if isinstance(what_i_see_now, list) else [])
        _render_list("Why That Matters", why_that_matters if isinstance(why_that_matters, list) else [])
        _render_list("The Good", the_good if isinstance(the_good, list) else [])
        _render_list("The Risk", the_risk if isinstance(the_risk, list) else [])

        sc = retail_summary.get("simple_conclusion") or ""
        if str(sc).strip():
            story.append(Spacer(1, 0.1 * inch))
            story.append(Paragraph("Simple Conclusion", heading_style))
            story.append(Paragraph(_escape(str(sc)), body_style))

        _render_list("Key Data Points Used", key_data_points if isinstance(key_data_points, list) else [])

        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph("Short Action Ideas", heading_style))
        if conservative:
            story.append(Paragraph(_escape(f"Conservative: {conservative}"), body_style))
        if tactical:
            story.append(Paragraph(_escape(f"Tactical: {tactical}"), body_style))
        if risk_control:
            story.append(Paragraph(_escape(f"Risk control: {risk_control}"), body_style))
    else:
        decision = rec_data.get("decision")
        decision_scope = rec_data.get("decision_scope")
        decision_rationale = rec_data.get("decision_rationale") or ""
        entry_triggers = rec_data.get("entry_triggers") or []
        watch_triggers = rec_data.get("watch_triggers") or []
        kill_criteria = rec_data.get("kill_criteria") or []
        decision_evidence = rec_data.get("decision_evidence") or []
        funds_to_consider = rec_data.get("funds_to_consider")

        if decision_scope == "pre_ipo_fund":
            vehicle_text = (
                funds_to_consider[0]
                if isinstance(funds_to_consider, list) and len(funds_to_consider) > 0
                else "Pre-IPO fund"
            )
        elif decision_scope == "post_ipo_direct":
            vehicle_text = "Post-IPO direct positioning"
        elif decision_scope == "no_trade":
            vehicle_text = "No trade"
        else:
            vehicle_text = "—"

        story.append(Paragraph("Decision Contract", heading_style))
        story.append(
            Paragraph(
                _escape(f"Decision: {decision or '—'} | Scope: {decision_scope or '—'}"),
                body_style,
            )
        )
        story.append(Spacer(1, 0.1 * inch))

        story.append(Paragraph("Vehicle", heading_style))
        story.append(Paragraph(_escape(str(vehicle_text)), body_style))
        story.append(Spacer(1, 0.1 * inch))

        story.append(Paragraph("Why Now", heading_style))
        story.append(
            Paragraph(
                _escape(decision_rationale or rec_data.get("plain_english_summary") or "—"),
                body_style,
            )
        )
        story.append(Spacer(1, 0.1 * inch))

        if isinstance(entry_triggers, list) and len(entry_triggers) > 0:
            story.append(Paragraph("Entry Triggers", heading_style))
            story.append(
                Paragraph(
                    _escape("; ".join(str(t) for t in entry_triggers[:20])),
                    body_style,
                )
            )
            story.append(Spacer(1, 0.1 * inch))

        if isinstance(watch_triggers, list) and len(watch_triggers) > 0:
            story.append(Paragraph("Watch Triggers", heading_style))
            story.append(
                Paragraph(
                    _escape("; ".join(str(t) for t in watch_triggers[:20])),
                    body_style,
                )
            )
            story.append(Spacer(1, 0.1 * inch))

        if isinstance(kill_criteria, list) and len(kill_criteria) > 0:
            story.append(Paragraph("Kill Criteria", heading_style))
            story.append(
                Paragraph(
                    _escape("; ".join(str(k) for k in kill_criteria[:20])),
                    body_style,
                )
            )
            story.append(Spacer(1, 0.1 * inch))

        if isinstance(decision_evidence, list) and len(decision_evidence) > 0:
            story.append(Paragraph("Decision Evidence", heading_style))
            story.append(
                Paragraph(
                    _escape("; ".join(str(e) for e in decision_evidence[:20])),
                    body_style,
                )
            )
            story.append(Spacer(1, 0.1 * inch))

        investment_action = rec_data.get("investment_action")
        if investment_action:
            story.append(Paragraph("Investment Action", heading_style))
            story.append(Paragraph(_escape(str(investment_action)), body_style))
            story.append(Spacer(1, 0.1 * inch))

        if isinstance(funds_to_consider, list) and funds_to_consider:
            story.append(Paragraph("Funds to Consider", heading_style))
            story.append(Paragraph(_escape(", ".join(str(f) for f in funds_to_consider)), body_style))
            story.append(Spacer(1, 0.1 * inch))

        what_to_watch = rec_data.get("what_to_watch")
        if isinstance(what_to_watch, list) and what_to_watch:
            story.append(Paragraph("What to Watch", heading_style))
            story.append(Paragraph(_escape("; ".join(str(w) for w in what_to_watch)), body_style))
            story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("Data sources", heading_style))
    sources_text = ", ".join(sources_active) if sources_active else "—"
    story.append(Paragraph(_escape(f"{sources_text} (retrieved: {sources_ts})"), body_style))
    story.append(Spacer(1, 0.15 * inch))

    story.append(
        Paragraph(
            _escape(
                f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}. "
                "This summary is for informational purposes only and does not constitute investment advice."
            ),
            ParagraphStyle("Disclaimer", parent=body_style, fontSize=7, textColor=colors.grey),
        )
    )

    doc.build(story)
    return buf.getvalue()
