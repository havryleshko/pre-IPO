from __future__ import annotations

from datetime import date, datetime
from typing import Any

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Collapsible, Static


class FinancialResultWidget(VerticalScroll, can_focus=True):
    BINDINGS = [
        ("j", "scroll_down", "Down"),
        ("k", "scroll_up", "Up"),
        ("pagedown", "page_down", "Page down"),
        ("pageup", "page_up", "Page up"),
        ("home", "scroll_home", "Home"),
        ("end", "scroll_end", "End"),
    ]

    DEFAULT_CSS = """
    FinancialResultWidget {
        overflow-y: auto;
        width: 100%;
        height: 1fr;
    }
    #result-main {
        width: 100%;
        height: auto;
    }
    #filing-collapsible {
        width: 100%;
    }
    #filing-body {
        width: 100%;
        height: auto;
    }
    #interpretation {
        width: 100%;
        height: auto;
    }
    """

    _OUTCOME_ORDER = [
        "ipo_price",
        "current_price",
        "perf_since_ipo",
        "peak_price",
        "peak_date",
        "trough_price",
        "trough_date",
        "lockup_cliff_date",
        "price_at_lockup_cliff",
        "recovered_to_ipo_date",
        "recovered_to_peak_date",
        "peak_multiple_vs_ipo",
        "trough_vs_ipo",
        "current_vs_peak",
    ]

    _OUTCOME_LABELS = {
        "ipo_price": "IPO price",
        "current_price": "Current price",
        "perf_since_ipo": "Performance since IPO",
        "peak_price": "Peak price",
        "peak_date": "Peak date",
        "trough_price": "Trough price",
        "trough_date": "Trough date",
        "lockup_cliff_date": "Lock-up cliff date",
        "price_at_lockup_cliff": "Price at lock-up cliff",
        "recovered_to_ipo_date": "Recovered to IPO date",
        "recovered_to_peak_date": "Recovered to peak date",
        "peak_multiple_vs_ipo": "Peak multiple vs IPO",
        "trough_vs_ipo": "Trough vs IPO",
        "current_vs_peak": "Current vs peak",
    }

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._data: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="result-main")
        with Collapsible(title="S-1 Filing Snapshot", id="filing-collapsible"):
            yield Static("", id="filing-body")
        yield Static("", id="interpretation")

    def set_data(self, data: dict[str, Any] | None) -> None:
        self._data = data
        self._refresh_sections()

    def _refresh_sections(self) -> None:
        main = self.query_one("#result-main", Static)
        filing = self.query_one("#filing-body", Static)
        filing_wrap = self.query_one("#filing-collapsible", Collapsible)
        interpretation = self.query_one("#interpretation", Static)

        if not self._data:
            main.update(Text(""))
            filing.update(Text(""))
            filing_wrap.display = False
            interpretation.update(Text(""))
            return

        main.update(self._build_main_group(self._data))
        filing_panel = self._build_filing_snapshot_panel(self._data)
        if filing_panel is None:
            filing_wrap.display = False
            filing.update(Text(""))
        else:
            filing_wrap.display = True
            filing.update(filing_panel)
        interpretation.update(self._build_interpretation_panel(self._data))

    def _build_main_group(self, data: dict[str, Any]) -> RenderableType:
        sections: list[RenderableType] = [
            self._build_reference_panel(data),
            self._build_key_claims_panel(data),
            self._build_outcome_panel(data),
            self._build_text_panel("Forecast Error", data.get("forecast_error", "—"), "magenta"),
            self._build_text_panel(
                "Predicted Pattern (pre-IPO basis)",
                data.get("predicted_pattern", "—"),
                "bright_cyan",
            ),
        ]

        claim_checks = self._build_claim_checks_panel(data)
        if claim_checks is not None:
            sections.append(claim_checks)

        news_claims = self._build_news_claims_panel(data)
        if news_claims is not None:
            sections.append(news_claims)

        return Group(*sections)

    def _build_reference_panel(self, data: dict[str, Any]) -> Panel:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Metric", style="bold cyan", justify="right", no_wrap=True)
        table.add_column("Value", style="white")
        table.add_row("Company (Ticker)", str(data.get("company", "—")))
        table.add_row(
            "Industry / Region",
            f"{data.get('industry', '—')} / {data.get('region', '—')}",
        )
        table.add_row("IPO Date", str(data.get("ipo_date", "—")))
        return Panel(table, title="Reference", border_style="bright_blue", padding=(1, 2))

    def _build_key_claims_panel(self, data: dict[str, Any]) -> Panel:
        content = Text(str(data.get("key_pre_ipo_claims", "—")), style="italic dim yellow")
        return Panel(
            content,
            title="Key Pre-IPO Claim(s)",
            subtitle="management expectations – read with salt",
            subtitle_align="left",
            border_style="yellow",
            padding=(1, 2),
        )

    def _build_outcome_panel(self, data: dict[str, Any]) -> Panel:
        outcome_data = data.get("outcome_data", {})
        perf = self._to_float(outcome_data.get("perf_since_ipo"))
        border = "green" if perf is not None and perf > 0 else "red"

        summary = Text(str(data.get("long_term_outcome_summary", "—")), style="bold white")

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Metric", style="bold cyan", justify="right", width=28, no_wrap=True)
        table.add_column("Value", justify="right", width=20)

        for key in self._OUTCOME_ORDER:
            value = outcome_data.get(key)
            label = self._OUTCOME_LABELS[key]
            table.add_row(label, self._style_outcome_value(key, value))

        body = Group(summary, Text(""), table)
        return Panel(
            body,
            title="Long-term Outcome (IPO → Apr 2026)",
            border_style=border,
            padding=(1, 2),
        )

    def _build_text_panel(self, title: str, value: Any, border_style: str) -> Panel:
        return Panel(Text(str(value), style="white"), title=title, border_style=border_style, padding=(1, 2))

    def _build_claim_checks_panel(self, data: dict[str, Any]) -> Panel | None:
        checks = data.get("s1_claim_checks") or []
        if not checks:
            return None
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("", width=3, justify="center")
        table.add_column("Check", style="bold white", width=52)
        table.add_column("Signal", style="white", width=10, no_wrap=True)
        table.add_column("Evidence", style="white")

        for item in checks:
            status = str(item.get("status", "unverifiable"))
            icon = "[?]"
            color = "cyan"
            signal = "Unknown"
            if status == "supported":
                icon = "[+]"
                color = "green"
                signal = "Yes"
            elif status == "missed":
                icon = "[!]"
                color = "red"
                signal = "No"
            elif status == "mixed":
                icon = "[~]"
                color = "yellow"
                signal = "Partial"
            evidence = str(item.get("quote") or item.get("rationale") or "—")
            table.add_row(
                Text(icon, style=color),
                str(item.get("label") or item.get("claim") or "—"),
                Text(signal, style=color),
                Text(evidence),
            )

        return Panel(table, title="S-1 Claim Checks", border_style="cyan", padding=(1, 2))

    def _build_news_claims_panel(self, data: dict[str, Any]) -> Panel | None:
        claims = data.get("news_claims") or []
        if not claims:
            return None

        bullets = [Text(f"• {str(claim)}", style="white") for claim in claims]
        return Panel(Group(*bullets), title="News Claims Extracted", border_style="cyan", padding=(1, 2))

    def _build_filing_snapshot_panel(self, data: dict[str, Any]) -> Panel | None:
        rows = data.get("filing_snapshot") or []
        filtered = [row for row in rows if self._has_meaningful_value(row.get("value"))]
        if not filtered:
            return None

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Field", style="bold cyan", justify="right", no_wrap=True)
        table.add_column("Value", style="white")
        for row in filtered:
            table.add_row(str(row.get("field", "—")), str(row.get("value", "—")))

        return Panel(table, border_style="bright_blue", padding=(1, 2))

    def _build_interpretation_panel(self, data: dict[str, Any]) -> Panel:
        return Panel(
            Text(str(data.get("interpretation", "—")), style="white"),
            title="Interpretation (model-generated)",
            border_style="white",
            padding=(1, 2),
        )

    def _style_outcome_value(self, key: str, value: Any) -> Text:
        raw_text = self._format_outcome_value(key, value)
        numeric = self._to_float(value)

        style = "white"
        if key in {"perf_since_ipo", "trough_vs_ipo", "current_vs_peak"} and numeric is not None:
            style = "green" if numeric > 0 else "red" if numeric < 0 else "white"
        elif key in {"peak_multiple_vs_ipo"} and numeric is not None:
            style = "green" if numeric >= 1 else "red"
        elif key in {"current_price", "peak_price", "price_at_lockup_cliff"} and numeric is not None:
            style = "green"
        elif key in {"trough_price"} and numeric is not None:
            style = "red"

        return Text(raw_text, style=style)

    def _format_outcome_value(self, key: str, value: Any) -> str:
        if value is None:
            return "—"

        if key in {"peak_date", "trough_date", "lockup_cliff_date", "recovered_to_ipo_date", "recovered_to_peak_date"}:
            return self._format_date(value)

        numeric = self._to_float(value)
        if numeric is None:
            return str(value)

        if key in {"ipo_price", "current_price", "peak_price", "trough_price", "price_at_lockup_cliff"}:
            return f"{numeric:.2f}"
        if key in {"perf_since_ipo", "trough_vs_ipo", "current_vs_peak"}:
            return f"{numeric:+.1f}%"
        if key == "peak_multiple_vs_ipo":
            return f"{numeric:.2f}x"
        return f"{numeric:.2f}"

    def _format_date(self, value: Any) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    def _has_meaningful_value(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip() != "" and value.strip().lower() not in {"none", "null", "n/a"}
        if isinstance(value, (int, float)):
            return value != 0
        return True

    def _to_float(self, value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip().replace("%", "").replace("x", "").replace(",", "")
            if cleaned.startswith("+"):
                cleaned = cleaned[1:]
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None
