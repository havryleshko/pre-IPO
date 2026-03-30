from __future__ import annotations

import json
from pathlib import Path

from tui.render import render_result_markdown, render_result_plain
from tui.types import SingleAgentResult


def export_all(*, analysis_id: str, result: SingleAgentResult, base_dir: str = "exports") -> Path:
    out_dir = Path(base_dir) / analysis_id
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "analysis.txt").write_text(render_result_plain(result), encoding="utf-8")
    (out_dir / "analysis.md").write_text(render_result_markdown(result), encoding="utf-8")
    (out_dir / "analysis.json").write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_dir

