import asyncio
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
    "Return ONLY valid JSON matching the schema — no markdown fences, no extra keys. "
    "Be brief: headline plus at most 2 short items per list."
)

_SCHEMA_DESCRIPTION = """{
  "headline": "<one short sentence verdict on the IPO outcome, grounded in news and price data>",
  "pre_ipo_story": ["<max 2 short bullets on what the S-1 and pre-IPO news claimed>"],
  "post_ipo_grounding": ["<max 2 short bullets on what actually happened post-IPO>"],
  "key_differences": ["<max 2 short bullets on the gap between claims and reality>"],
  "watch_items": ["<max 2 short bullets on what to monitor next>"],
  "sources_cited": ["<max 4 short source labels or URLs used>"]
}"""


def _clean_json_text(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :].strip()
    if text.endswith("```"):
        text = text[:-3].rstrip()
    return text


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
        claims_json = json.dumps([c.model_dump(mode="json") for c in prediction_claims[:4]], indent=2)
        sections.append(f"Prediction claims from S-1:\n{claims_json}")

    if filing_facts:
        facts_json = json.dumps([f.model_dump(mode="json") for f in filing_facts[:6]], indent=2)
        sections.append(f"Filing facts:\n{facts_json}")

    key_risks = parser_output.get("key_risks")
    if isinstance(key_risks, list) and key_risks:
        sections.append(f"Key risks from S-1: {'; '.join(str(r) for r in key_risks[:4])}")

    if news_articles:
        news_lines: list[str] = []
        for article in news_articles[:2]:
            title = article.get("title") or ""
            summary = article.get("summary") or article.get("description") or ""
            url = article.get("url") or ""
            published = article.get("published_at") or article.get("publishedAt") or ""
            date_tag = f" [{published[:10]}]" if published else ""
            news_lines.append(f"  - {title}{date_tag}: {summary[:220]} ({url})")
        sections.append("News coverage (use heavily for post_ipo_grounding, watch_items, and sources_cited):\n" + "\n".join(news_lines))

    sections.append(f"\nReturn JSON matching this schema:\n{_SCHEMA_DESCRIPTION}")
    return "\n\n".join(sections)


class NarrativeSynthesiser:
    async def synthesise(
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
            raw = await asyncio.to_thread(
                self._fetch_narrative_text,
                prompt,
            )
            data = json.loads(_clean_json_text(raw))
            return NarrativeReport.model_validate(data)
        except Exception as exc:
            logger.warning("NarrativeSynthesiser failed: %s", exc)
            return None

    def _fetch_narrative_text(self, prompt: str) -> str:
        client = anthropic.Anthropic(api_key=settings.llm_api_key)
        message = client.messages.create(
            model=settings.llm_model,
            max_tokens=2000,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text_blocks = [b for b in message.content if b.type == "text"]
        return text_blocks[0].text if text_blocks else ""
