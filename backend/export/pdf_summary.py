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
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph(f"Analysis date: {analysis_date}", body_style))
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

    investment_action = rec_data.get("investment_action")
    if investment_action:
        story.append(Paragraph("Investment Action", heading_style))
        story.append(Paragraph(str(investment_action), body_style))
        story.append(Spacer(1, 0.1 * inch))

    funds_to_consider = rec_data.get("funds_to_consider")
    if isinstance(funds_to_consider, list) and funds_to_consider:
        story.append(Paragraph("Funds to Consider", heading_style))
        story.append(Paragraph(", ".join(str(f) for f in funds_to_consider), body_style))
        story.append(Spacer(1, 0.1 * inch))

    what_to_watch = rec_data.get("what_to_watch")
    if isinstance(what_to_watch, list) and what_to_watch:
        story.append(Paragraph("What to Watch", heading_style))
        story.append(Paragraph("; ".join(str(w) for w in what_to_watch), body_style))
        story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("Data sources", heading_style))
    sources_text = ", ".join(sources_active) if sources_active else "—"
    story.append(Paragraph(f"{sources_text} (retrieved: {sources_ts})", body_style))
    story.append(Spacer(1, 0.15 * inch))

    story.append(
        Paragraph(
            f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}. "
            "This summary is for informational purposes only and does not constitute investment advice.",
            ParagraphStyle("Disclaimer", parent=body_style, fontSize=7, textColor=colors.grey),
        )
    )

    doc.build(story)
    return buf.getvalue()
