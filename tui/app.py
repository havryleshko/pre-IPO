from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from rich.panel import Panel
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Input, Static

from tui.api import ApiClient
from tui.widgets.result import FinancialResultWidget

@dataclass(frozen=True)
class _RunContext:
    analysis_id: str
    company_name: str
    created_at: datetime


class PreIPOTui(App):
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("enter", "start_analysis", "Start"),
        ("r", "refresh", "Refresh"),
        ("e", "export", "Export"),
    ]

    CSS = """
    #root { padding: 1 2; height: 1fr; }
    #top-bar { height: 3; dock: top; padding: 0 2; margin-bottom: 1; }
    #header-left { width: 1fr; height: 3; align: left middle; }
    #header-title { color: cyan; text-style: bold; width: 1fr; content-align: left middle; }
    #price-badge { width: auto; min-width: 12; height: 1; content-align: center middle; padding: 0 1; }
    #controls { width: auto; height: 3; align: right middle; }
    #company { width: 30; margin-right: 1; }
    #status { height: 3; margin-bottom: 1; }
    #result { height: 1fr; }
    """

    status_text = reactive("Idle")
    tool_call = reactive("")

    def __init__(self) -> None:
        super().__init__()
        self._api = ApiClient()
        self._run: _RunContext | None = None
        self._progress_task: asyncio.Task[None] | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-bar"):
            with Horizontal(id="header-left"):
                yield Static("—", id="header-title")
                yield Static(" -- ", id="price-badge")
            with Horizontal(id="controls"):
                yield Input(placeholder="e.g. Arm Holdings or RKLB", id="company")
                yield Button("Start", id="start", variant="primary")
                yield Button("Refresh", id="refresh")
                yield Button("Export", id="export")
        with Vertical(id="root"):
            yield Static("", id="status")
            yield FinancialResultWidget(id="result")

    def watch_status_text(self, value: str) -> None:
        text_style = "bold white"
        lower = value.lower()
        if "status=failed" in lower or lower.startswith("failed"):
            text_style = "bold red"
        elif "status=completed_with_flags" in lower:
            text_style = "bold yellow"
        elif "status=completed" in lower:
            text_style = "bold green"
        elif "status=running" in lower or "creating analysis" in lower:
            text_style = "bold cyan"
        panel = Panel(Text(value, style=text_style), title="Status", border_style="bright_cyan")
        self.query_one("#status", Static).update(panel)

    def watch_tool_call(self, value: str) -> None:
        suffix = f" | tool_call={value}" if value else ""
        self.watch_status_text(f"{self.status_text.split(' | ')[0]}{suffix}")

    async def on_mount(self) -> None:
        self.watch_status_text("Status - idle")
        self.query_one("#company", Input).focus()

    @on(Button.Pressed, "#start")
    async def start_clicked(self) -> None:
        await self._start_analysis()

    @on(Input.Submitted, "#company")
    async def company_submitted(self, _: Input.Submitted) -> None:
        await self._start_analysis()

    async def action_start_analysis(self) -> None:
        await self._start_analysis()

    @on(Button.Pressed, "#refresh")
    async def refresh_clicked(self) -> None:
        await self.refresh_analysis()

    async def action_refresh(self) -> None:
        await self.refresh_analysis()

    @on(Button.Pressed, "#export")
    async def export_clicked(self) -> None:
        await self._export()

    async def action_export(self) -> None:
        await self._export()

    async def _start_analysis(self) -> None:
        company = self.query_one("#company", Input).value.strip()
        if not company:
            self.watch_status_text("Missing company name.")
            return

        self.watch_status_text("Status - running | creating analysis")
        self.query_one("#header-title", Static).update(f"{company}")
        self.query_one("#price-badge", Static).update(Text(" -- ", style="black on white"))

        try:
            created = await self._api.create_analysis(company)
        except httpx.HTTPStatusError as exc:
            self.watch_status_text(f"Create failed: HTTP {exc.response.status_code}")
            return
        except Exception as exc:
            self.watch_status_text(f"Create failed: {exc}")
            return

        self._run = _RunContext(
            analysis_id=created.analysis_id,
            company_name=created.company_name,
            created_at=created.created_at,
        )
        self.status_text = f"Status - {created.status} | analysis_id={created.analysis_id}"
        self.tool_call = ""

        if self._progress_task is not None:
            self._progress_task.cancel()
        self._progress_task = asyncio.create_task(self._consume_progress(created.analysis_id))

        await self.refresh_analysis()

    async def refresh_analysis(self) -> None:
        if self._run is None:
            self.watch_status_text("No analysis yet.")
            return

        try:
            data = await self._api.get_analysis(self._run.analysis_id)
        except httpx.HTTPStatusError as exc:
            self.watch_status_text(f"Refresh failed: HTTP {exc.response.status_code}")
            return
        except Exception as exc:
            self.watch_status_text(f"Refresh failed: {exc}")
            return

        last_agent = data.last_completed_agent or "-"
        self.status_text = f"Status - {data.status} | analysis_id={data.analysis_id} | last_completed_agent={last_agent}"

        if data.analysis_result is None:
            self.query_one("#header-title", Static).update(f"{data.company_name}")
            self.query_one("#price-badge", Static).update(Text(" -- ", style="black on white"))
            self.query_one("#result", FinancialResultWidget).set_data(
                {
                    "ticker": "—",
                    "company": data.company_name,
                    "industry": "—",
                    "region": "—",
                    "ipo_date": "—",
                    "key_pre_ipo_claims": "—",
                    "long_term_outcome_summary": "—",
                    "forecast_error": "No structured result returned yet.",
                    "predicted_pattern": "—",
                    "outcome_data": {},
                    "s1_claim_checks": [],
                    "news_claims": [],
                    "filing_snapshot": [],
                    "interpretation": "Analysis running..." if data.status == "running" else "No structured result returned.",
                }
            )
            return

        mapped = self._map_result_to_widget_data(data.analysis_result)
        title = f"{mapped.get('ticker', '—')} {mapped.get('company', data.company_name)}".strip()
        self.query_one("#header-title", Static).update(title)
        self.query_one("#price-badge", Static).update(self._build_price_badge(mapped))
        self.query_one("#result", FinancialResultWidget).set_data(mapped)

    def _map_result_to_widget_data(self, result: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ticker": "—",
            "company": result.company_name,
            "industry": "—",
            "region": "—",
            "ipo_date": "—",
            "key_pre_ipo_claims": "—",
            "long_term_outcome_summary": "—",
            "forecast_error": "—",
            "predicted_pattern": "—",
            "outcome_data": {},
            "s1_claim_checks": [],
            "news_claims": [],
            "filing_snapshot": [],
            "interpretation": "—",
        }

        row = result.reference_table_row
        if row is not None:
            payload["company"] = row.company_ticker
            payload["ticker"] = self._extract_ticker(row.company_ticker)
            industry, region = self._split_industry_region(row.industry_region)
            payload["industry"] = industry
            payload["region"] = region
            payload["ipo_date"] = row.ipo_date
            payload["key_pre_ipo_claims"] = row.key_pre_ipo_claims
            payload["forecast_error"] = row.forecast_error
            payload["predicted_pattern"] = row.predicted_pattern

        if result.company_profile is not None:
            payload["ticker"] = result.company_profile.ticker or payload["ticker"]
            payload["ipo_date"] = str(result.company_profile.ipo_date or payload["ipo_date"])
            industry, region = self._split_industry_region(result.company_profile.industry_region)
            if industry != "—":
                payload["industry"] = industry
            if region != "—":
                payload["region"] = region

        if result.outcome_metrics is not None:
            om = result.outcome_metrics
            outcome_data = {
                "ipo_price": om.ipo_price,
                "current_price": om.current_price,
                "perf_since_ipo": om.performance_since_ipo_pct,
                "peak_price": om.peak_price,
                "peak_date": om.peak_date,
                "trough_price": om.trough_price,
                "trough_date": om.trough_date,
                "lockup_cliff_date": om.lock_up_cliff_date,
                "price_at_lockup_cliff": om.price_at_lock_up_cliff,
                "recovered_to_ipo_date": om.recovered_to_ipo_date,
                "recovered_to_peak_date": om.recovered_to_peak_date,
                "peak_multiple_vs_ipo": None,
                "trough_vs_ipo": None,
                "current_vs_peak": None,
            }
            if om.ipo_price not in (None, 0):
                if om.peak_price is not None:
                    outcome_data["peak_multiple_vs_ipo"] = om.peak_price / om.ipo_price
                if om.trough_price is not None:
                    outcome_data["trough_vs_ipo"] = ((om.trough_price - om.ipo_price) / om.ipo_price) * 100.0
            if om.current_price is not None and om.peak_price not in (None, 0):
                outcome_data["current_vs_peak"] = ((om.current_price - om.peak_price) / om.peak_price) * 100.0
            payload["outcome_data"] = outcome_data

        payload["s1_claim_checks"] = [
            {
                "label": c.claim_id,
                "status": c.status,
                "quote": c.evidence_quotes[0] if c.evidence_quotes else None,
                "rationale": c.rationale,
                "confidence": c.confidence,
            }
            for c in result.claim_checks
        ]

        payload["news_claims"] = [item.evidence_quote for item in result.news_derived_claims]

        payload["filing_snapshot"] = [
            {"field": fact.metric, "value": fact.value if fact.value is not None else fact.units}
            for fact in result.filing_facts
        ]

        if result.narrative is not None:
            n = result.narrative
            parts: list[str] = [n.headline]
            if n.pre_ipo_story:
                parts.append(" ".join(n.pre_ipo_story))
            if n.post_ipo_grounding:
                parts.append(" ".join(n.post_ipo_grounding))
            if n.key_differences:
                parts.append(" ".join(n.key_differences))
            if n.watch_items:
                parts.append(" ".join(n.watch_items))
            payload["interpretation"] = "\n\n".join([p for p in parts if p]).strip()

        if result.realized_outcome is not None:
            payload["long_term_outcome_summary"] = result.realized_outcome.long_term_outcome
            payload["forecast_error"] = result.realized_outcome.forecast_error
        elif row is not None:
            payload["long_term_outcome_summary"] = row.long_term_outcome

        return payload

    def _extract_ticker(self, company_field: str) -> str:
        text = company_field.strip()
        if "(" in text and ")" in text:
            inner = text[text.rfind("(") + 1 : text.rfind(")")].strip()
            if inner:
                return inner
        pieces = text.split()
        return pieces[-1] if pieces else "—"

    def _split_industry_region(self, raw: str) -> tuple[str, str]:
        if not raw:
            return "—", "—"
        parts = [p.strip() for p in raw.split("/")]
        if len(parts) >= 2:
            return parts[0], parts[1]
        return parts[0], "—"

    def _build_price_badge(self, payload: dict[str, Any]) -> Text:
        outcome = payload.get("outcome_data", {})
        current = outcome.get("current_price")
        delta = outcome.get("current_vs_peak")
        if current is None:
            return Text(" -- ", style="black on white")
        if delta is None:
            return Text(f" {float(current):.2f} ", style="black on white")
        sign = "+" if float(delta) >= 0 else ""
        style = "black on green" if float(delta) >= 0 else "white on red"
        return Text(f" {float(current):.2f} ({sign}{float(delta):.1f}%) ", style=style)

    async def _export(self) -> None:
        if self._run is None:
            self.watch_status_text("No analysis yet.")
            return

        try:
            data = await self._api.get_analysis(self._run.analysis_id)
        except httpx.HTTPStatusError as exc:
            self.watch_status_text(f"Export fetch failed: HTTP {exc.response.status_code}")
            return
        except Exception as exc:
            self.watch_status_text(f"Export fetch failed: {exc}")
            return

        if data.analysis_result is None:
            self.watch_status_text("No analysis_result to export yet.")
            return

        try:
            await self._api.export_all(self._run.analysis_id, data.analysis_result)
        except Exception as exc:
            self.watch_status_text(f"Export failed: {exc}")
            return

        self.watch_status_text(f"Status - completed | exported to exports/{self._run.analysis_id}/")

    async def _consume_progress(self, analysis_id: str) -> None:
        try:
            async for ev in self._api.progress_events(analysis_id):
                if ev.type != "agent_status":
                    continue
                if ev.agent_name != "single_agent":
                    continue
                if ev.tool_call:
                    self.tool_call = ev.tool_call
                if ev.status in ("completed", "failed"):
                    await self.refresh_analysis()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            self.watch_status_text(f"progress error: {exc}")

    async def on_unmount(self) -> None:
        if self._progress_task is not None:
            self._progress_task.cancel()
        await self._api.aclose()


def run() -> None:
    PreIPOTui().run()
