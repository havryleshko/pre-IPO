import json
import logging
from typing import Any

import anthropic

from backend.config.settings import settings
from backend.models.single_agent_result import (
    FilingFact,
    NarrativeReport,
    OutcomeMetrics,
    PredictionClaim,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert IPO analyst. Given structured data about a company's IPO, "
    "produce a concise analytical narrative in JSON. "
    "Return ONLY valid JSON matching the schema — no markdown fences, no extra keys."
)

_SCHEMA_DESCRIPTION = """{
  "headline": "<one sentence verdict on the IPO outcome, grounded in news and price data>",
  "pre_ipo_story": ["<what the S-1 and pre-IPO news claimed about the company>"],
  "post_ipo_grounding": ["<what actually happened post-IPO, drawn from news coverage and outcome metrics>"],
  "key_differences": ["<gaps between S-1 claims and post-IPO news/price reality>"],
  "watch_items": ["<forward-looking items from recent news that investors should monitor>"],
  "sources_cited": ["<article titles, URLs, or filing references used>"]
}"""


def _build_prompt(
    company_name: str,
    parser_output: dict[str, Any],
    news_articles: list[dict[str, Any]],
    outcome_metrics: OutcomeMetrics | None,
    prediction_claims: list[PredictionClaim],
    filing_facts: list[FilingFact],
) -> str:
    sections: list[str] = [f"Company: {company_name}"]

    if outcome_metrics:
        sections.append(f"Outcome metrics: {outcome_metrics.model_dump_json()}")

    if prediction_claims:
        claims_json = json.dumps([c.model_dump(mode="json") for c in prediction_claims[:6]], indent=2)
        sections.append(f"Prediction claims from S-1:\n{claims_json}")

    if filing_facts:
        facts_json = json.dumps([f.model_dump(mode="json") for f in filing_facts[:8]], indent=2)
        sections.append(f"Filing facts:\n{facts_json}")

    key_risks = parser_output.get("key_risks")
    if isinstance(key_risks, list) and key_risks:
        sections.append(f"Key risks from S-1: {'; '.join(str(r) for r in key_risks[:4])}")

    if news_articles:
        news_lines: list[str] = []
        for article in news_articles[:5]:
            title = article.get("title") or ""
            summary = article.get("summary") or article.get("description") or ""
            url = article.get("url") or ""
            published = article.get("published_at") or article.get("publishedAt") or ""
            date_tag = f" [{published[:10]}]" if published else ""
            news_lines.append(f"  - {title}{date_tag}: {summary[:400]} ({url})")
        sections.append("News coverage (use heavily for post_ipo_grounding, watch_items, and sources_cited):\n" + "\n".join(news_lines))

    sections.append(f"\nReturn JSON matching this schema:\n{_SCHEMA_DESCRIPTION}")
    return "\n\n".join(sections)


class NarrativeSynthesiser:
    def synthesise(
        self,
        company_name: str,
        parser_output: dict[str, Any],
        harvester_output: dict[str, Any],
        outcome_metrics: OutcomeMetrics | None,
        prediction_claims: list[PredictionClaim],
        filing_facts: list[FilingFact],
    ) -> NarrativeReport | None:
        if not settings.llm_api_key:
            logger.info("llm_api_key not set — skipping narrative synthesis")
            return None

        news_articles: list[dict[str, Any]] = []
        raw_articles = harvester_output.get("news_articles")
        if isinstance(raw_articles, list):
            for a in raw_articles:
                if isinstance(a, dict):
                    news_articles.append(a)

        prompt = _build_prompt(
            company_name=company_name,
            parser_output=parser_output,
            news_articles=news_articles,
            outcome_metrics=outcome_metrics,
            prediction_claims=prediction_claims,
            filing_facts=filing_facts,
        )

        try:
            client = anthropic.Anthropic(api_key=settings.llm_api_key)
            message = client.messages.create(
                model=settings.llm_model,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text_blocks = [b for b in message.content if b.type == "text"]
            raw = text_blocks[0].text if text_blocks else ""
            data = json.loads(raw)
            return NarrativeReport.model_validate(data)
        except Exception as exc:
            logger.warning("NarrativeSynthesiser failed: %s", exc)
            return None
