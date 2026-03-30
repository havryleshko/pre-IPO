from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tui.export import export_all
from tui.render import render_result_markdown, render_result_plain
from tui.types import (
    ClaimCheck,
    OutcomeMetrics,
    PatternFlag,
    PredictionClaim,
    SingleAgentResult,
)


def _sample_result() -> SingleAgentResult:
    return SingleAgentResult(
        company_name="TestCo",
        generated_at=datetime.now(timezone.utc),
        prediction_claims=[
            PredictionClaim(
                claim_id="c1",
                claim_type="growth",
                prediction_text="Revenue will grow fast.",
                source="internet",
                source_url=None,
                published_at=None,
            )
        ],
        filing_facts=[],
        outcome_metrics=OutcomeMetrics(
            ipo_price=10.0,
            current_price=12.5,
            performance_since_ipo_pct=25.0,
        ),
        claim_checks=[
            ClaimCheck(
                claim_id="c1",
                status="supported",
                evidence_quotes=["S-1 projection: X", "10-K actual: Y"],
                confidence="high",
            )
        ],
        patterns=[PatternFlag(signal="Lock-up cliff stress", was_visible_at_ipo=True, outcome="Down 20% after lockup")],
    )


def test_render_plain_contains_sections() -> None:
    s = render_result_plain(_sample_result())
    assert "TestCo" in s
    assert "Outcome" in s
    assert "ClaimChecks" in s
    assert "Patterns" in s


def test_render_markdown_contains_headers() -> None:
    s = render_result_markdown(_sample_result())
    assert s.startswith("# TestCo")
    assert "## Outcome" in s
    assert "## Claim checks" in s


def test_export_all_writes_three_files(tmp_path: Path) -> None:
    out = export_all(analysis_id="aid-1", result=_sample_result(), base_dir=str(tmp_path))
    txt = out / "analysis.txt"
    md = out / "analysis.md"
    js = out / "analysis.json"
    assert txt.is_file()
    assert md.is_file()
    assert js.is_file()
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert payload["company_name"] == "TestCo"

