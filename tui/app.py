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
from textual.widgets import Button, Footer, Header, Input, Label, Static

from tui.api import ApiClient, ProgressEvent
from tui.render import render_result_plain


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
    #root { padding: 1 2; }
    #controls { height: auto; margin-bottom: 1; }
    #company { width: 1fr; }
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
        yield Header()
        with Vertical(id="root"):
            with Horizontal(id="controls"):
                yield Label("Company or ticker")
                yield Input(placeholder="e.g. Arm Holdings or RKLB", id="company")
                yield Button("Start", id="start", variant="primary")
                yield Button("Refresh", id="refresh")
                yield Button("Export", id="export")
            yield Static("", id="status")
            yield Static("", id="result")
        yield Footer()

    def watch_status_text(self, value: str) -> None:
        panel = Panel(
            Text(value, style="bold cyan"),
            title="Status",
            border_style="cyan",
        )
        self.query_one("#status", Static).update(panel)

    def watch_tool_call(self, value: str) -> None:
        suffix = f" | tool_call={value}" if value else ""
        self.watch_status_text(f"{self.status_text.split(' | ')[0]}{suffix}")

    async def on_mount(self) -> None:
        self.watch_status_text("Idle")
        self.query_one("#company", Input).focus()

    @on(Button.Pressed, "#start")
    async def start_clicked(self) -> None:
        await self._start_analysis()

    @on(Input.Submitted, "#company")
    async def company_submitted(self, _: Input.Submitted) -> None:
        await self._start_analysis()

    async def action_start_analysis(self) -> None:
        await self._start_analysis()

    async def _start_analysis(self) -> None:
        company = self.query_one("#company", Input).value.strip()
        if not company:
            self.watch_status_text("Missing company name.")
            return

        self.watch_status_text("Creating analysis…")
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
        self.status_text = f"analysis_id={created.analysis_id} status={created.status}"
        self.tool_call = ""

        if self._progress_task is not None:
            self._progress_task.cancel()
        self._progress_task = asyncio.create_task(self._consume_progress(created.analysis_id))

        await self.refresh_analysis()

    @on(Button.Pressed, "#refresh")
    async def refresh_clicked(self) -> None:
        await self.refresh_analysis()

    async def action_refresh(self) -> None:
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
        self.status_text = (
            f"analysis_id={data.analysis_id} status={data.status} last_completed_agent={data.last_completed_agent}"
        )
        if data.analysis_result is None:
            if data.status in ("completed", "completed_with_flags", "failed"):
                msg = (
                    "No structured result returned (invalid or empty final_report). "
                    "Check API logs or database for this analysis_id."
                    if data.status != "failed"
                    else "Analysis failed. Check API logs."
                )
                self.query_one("#result", Static).update(
                    Panel(Text(msg, style="yellow"), title="Result", border_style="yellow")
                )
            else:
                self.query_one("#result", Static).update(
                    Panel(Text("Analysis running...", style="yellow"), title="Result", border_style="yellow")
                )
            return
        body = render_result_plain(data.analysis_result)
        self.query_one("#result", Static).update(
            Panel(Text(body), title=f"Result - {data.company_name}", border_style="green")
        )

    @on(Button.Pressed, "#export")
    async def export_clicked(self) -> None:
        await self._export()

    async def action_export(self) -> None:
        await self._export()

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
        self.watch_status_text(f"Exported to exports/{self._run.analysis_id}/")

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

