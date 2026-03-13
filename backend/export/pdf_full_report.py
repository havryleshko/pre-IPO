import io
import logging
from datetime import datetime
from typing import Any
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "This report is for informational purposes only and does not constitute investment advice. "
)


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


async def generate_full_report_pdf(record: dict[str, Any]) -> bytes:
    company_name = record.get("company_name") or "IPO Analysis"
    created_at = record.get("created_at")
    analysis_date = created_at.strftime("%Y-%m-%d") if isinstance(created_at, datetime) else "—"
    scenario_data = record.get("scenario_output") or {}
    rec_data = record.get("recommendation_output") or {}
    harvester_data = record.get("harvester_output") or {}

    scenarios = _get(scenario_data, "scenarios") or {}
    recommendations = _get(rec_data, "recommendations") or {}
    plain_summary = _get(rec_data, "plain_english_summary") or ""
    fred_data = _get(harvester_data, "fred_data") or {}
    yahoo_data = _get(harvester_data, "yahoo_finance_data") or {}
    twitter_data = _get(harvester_data, "twitter_data") or {}
    key_quotes = _get(twitter_data, "key_quotes") or []
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
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=12,
        alignment=1,
    )
    cover_sub_style = ParagraphStyle(
        "CoverSub",
        parent=styles["Normal"],
        fontSize=11,
        alignment=1,
        spaceAfter=24,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading1"],
        fontSize=14,
        spaceBefore=12,
        spaceAfter=8,
    )
    heading_style = ParagraphStyle(
        "Heading",
        parent=styles["Heading2"],
        fontSize=11,
        spaceAfter=6,
    )
    body_style = styles["Normal"]

    story = []

    story.append(Spacer(1, 2 * inch))
    story.append(Paragraph(_escape(company_name), title_style))
    story.append(Paragraph(f"IPO Analysis Report", cover_sub_style))
    story.append(Paragraph(f"Analysis date: {analysis_date}", cover_sub_style))
    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph(_escape(DISCLAIMER), ParagraphStyle("Disclaimer", parent=body_style, fontSize=9, alignment=1, textColor=colors.grey)))
    story.append(PageBreak())

    story.append(Paragraph("Executive Summary", section_style))
    story.append(Paragraph(_escape(plain_summary) if plain_summary else "—", body_style))
    story.append(PageBreak())

    story.append(Paragraph("1. Company Overview", section_style))
    story.append(Paragraph(_escape(plain_summary) if plain_summary else "—", body_style))
    story.append(PageBreak())

    story.append(Paragraph("2. Market Context", section_style))
    fed_rate = _get(fred_data, "fed_funds_rate")
    market_cond = _get(fred_data, "market_conditions") or "—"
    sector_perf = _get(yahoo_data, "sector_90d_performance")
    comps = _get(yahoo_data, "comparable_companies") or []
    story.append(Paragraph(company_name, heading_style))
    ctx_parts = []
    if fed_rate is not None:
        ctx_parts.append(f"Fed funds rate: {_fmt(fed_rate)}%")
    ctx_parts.append(f"Market conditions: {_escape(str(market_cond))}")
    if sector_perf is not None:
        ctx_parts.append(f"Sector 90-day performance: {_fmt(sector_perf)}%")
    story.append(Paragraph("; ".join(ctx_parts) if ctx_parts else "—", body_style))
    if comps:
        story.append(Paragraph(f"Comparable companies: {', '.join(comps)}", body_style))
    story.append(PageBreak())

    story.append(Paragraph("3. Scenario Analysis", section_style))
    pess = scenarios.get("pessimistic") or {}
    real = scenarios.get("realistic") or {}
    opt = scenarios.get("optimistic") or {}

    for label, data in [("Pessimistic", pess), ("Realistic", real), ("Optimistic", opt)]:
        pct = data.get("probability", 0)
        story.append(Paragraph(f"{label} ({_fmt_pct(pct)})", heading_style))
        story.append(Paragraph(f"Rationale: {_escape(str(data.get('weighting_rationale', '—')))}", body_style))
        drivers = data.get("drivers") or []
        if drivers:
            story.append(Paragraph("Drivers: " + "; ".join(_escape(str(d)) for d in drivers[:5]), body_style))
        risks = data.get("key_risks") or []
        if risks:
            story.append(Paragraph("Key risks: " + "; ".join(_escape(str(r)) for r in risks[:5]), body_style))
        pt = data.get("price_targets") or {}
        story.append(Paragraph(f"Price targets: 30d {_fmt(pt.get('30_days'))} | 90d {_fmt(pt.get('90_days'))} | 1yr {_fmt(pt.get('1_year'))}", body_style))
        story.append(Spacer(1, 0.2 * inch))

    story.append(PageBreak())

    story.append(Paragraph("4. Recommendations", section_style))
    for label, key in [("Pessimistic", "pessimistic"), ("Realistic", "realistic"), ("Optimistic", "optimistic")]:
        rec = recommendations.get(key) or {}
        story.append(Paragraph(label, heading_style))
        story.append(Paragraph(f"Positioning: {_escape(str(rec.get('recommended_positioning', '—')))}", body_style))
        story.append(Paragraph(f"Rationale: {_escape(str(rec.get('rationale', '—')))}", body_style))
        story.append(Paragraph(f"Risk warning: {_escape(str(rec.get('risk_warning', '—')))}", body_style))
        para = rec.get("client_paragraph") or ""
        if para:
            story.append(Paragraph(_escape(para), body_style))
        story.append(Spacer(1, 0.15 * inch))

    story.append(PageBreak())

    story.append(Paragraph("5. Supporting Evidence", section_style))
    if key_quotes:
        for q in key_quotes[:10]:
            author = q.get("author", "—")
            role = q.get("role", "")
            quote = q.get("quote", "—")
            story.append(Paragraph(f"<b>{_escape(author)}</b> ({_escape(role)}): {_escape(str(quote))}", body_style))
            story.append(Spacer(1, 0.1 * inch))
    else:
        story.append(Paragraph("No key quotes available.", body_style))

    story.append(PageBreak())

    story.append(Paragraph("6. Data Sources", section_style))
    sources_text = ", ".join(sources_active) if sources_active else "—"
    story.append(Paragraph(f"{sources_text}", body_style))
    story.append(Paragraph(f"Retrieved: {sources_ts}", body_style))
    story.append(PageBreak())

    story.append(Paragraph("Disclaimer", section_style))
    story.append(Paragraph(_escape(DISCLAIMER), body_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(
        Paragraph(
            f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}.",
            ParagraphStyle("Footer", parent=body_style, fontSize=8, textColor=colors.grey),
        )
    )

    doc.build(story)
    return buf.getvalue()
