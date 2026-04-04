from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.agents.narrative_synthesiser import NarrativeSynthesiser, _clean_json_text
from backend.models.single_agent_result import NarrativeReport


def test_clean_json_text_strips_markdown_fences() -> None:
    raw = """```json
{"headline":"ok","pre_ipo_story":[],"post_ipo_grounding":[],"key_differences":[],"watch_items":[],"sources_cited":[]}
```"""

    cleaned = _clean_json_text(raw)

    assert cleaned == (
        '{"headline":"ok","pre_ipo_story":[],"post_ipo_grounding":[],'
        '"key_differences":[],"watch_items":[],"sources_cited":[]}'
    )


@pytest.mark.asyncio
async def test_synthesise_accepts_fenced_json_response() -> None:
    class FakeTextBlock:
        type = "text"
        text = """```json
{"headline":"ok","pre_ipo_story":["a"],"post_ipo_grounding":["b"],"key_differences":["c"],"watch_items":["d"],"sources_cited":["e"]}
```"""

    class FakeMessages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(content=[FakeTextBlock()])

    class FakeAnthropic:
        def __init__(self, api_key: str) -> None:
            self.messages = FakeMessages()

    with (
        patch("backend.agents.narrative_synthesiser.settings.llm_api_key", "test-key"),
        patch("backend.agents.narrative_synthesiser.settings.llm_model", "claude-test"),
        patch("backend.agents.narrative_synthesiser.anthropic.Anthropic", FakeAnthropic),
    ):
        result = await NarrativeSynthesiser().synthesise(
            company_name="TestCo",
            parser_output={},
            harvester_output={"news_articles": []},
            outcome_metrics=None,
            prediction_claims=[],
            filing_facts=[],
        )

    assert isinstance(result, NarrativeReport)
    assert result.headline == "ok"
