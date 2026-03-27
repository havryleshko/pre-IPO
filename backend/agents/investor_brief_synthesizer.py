import json
import logging
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from backend.config.settings import get_settings
from backend.database.queries import get_analysis_by_id, save_investor_brief
from backend.models.investor_brief import InvestorBrief
from backend.services.agent_run_logger import log_agent_run_completed, log_agent_run_failed, log_agent_run_start

logger = logging.getLogger(__name__)


class InvestorBriefSynthesizerInput(BaseModel):
    analysis_id: str


class InvestorBriefSynthesizer:
    def __init__(self, llm: ChatOpenAI | None = None) -> None:
        if llm is None:
            settings = get_settings()
            self._llm = ChatOpenAI(
                model=settings.llm_model,
                temperature=0.0,
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
            )
        else:
            self._llm = llm

    async def run(self, payload: InvestorBriefSynthesizerInput) -> dict[str, Any] | None:
        run_record = await log_agent_run_start(
            analysis_id=payload.analysis_id,
            agent_name="investor_brief_synthesizer",
            input_reference=f"analysis_id={payload.analysis_id}"
        )
        run_id = str(run_record["id"]) if run_record else ""
        
        try:
            analysis = await get_analysis_by_id(payload.analysis_id)
            if not analysis:
                raise ValueError(f"Analysis {payload.analysis_id} not found")

            company_name = analysis.get("company_name", "Unknown Company")
            harvester_output = analysis.get("harvester_output") or {}
            parser_output = analysis.get("parser_output") or {}
            scenario_output = analysis.get("scenario_output") or {}

            # Prepare context
            context_str = json.dumps(
                {
                    "harvester_output": harvester_output,
                    "parser_output": parser_output,
                    "scenario_output": scenario_output,
                },
                default=str,
            )

            prompt = f"""You are a senior equity analyst creating a concise pre-IPO investor brief for a retail audience.
Your objective is to synthesise the provided data into a single hybrid output containing both structured fields and a markdown narrative.

Rules:
1. "overview_markdown": Write a short, plain-language overview of the company's equity, cap table, and valuation context (if available). Be honest if filing data is missing or thin.
2. Use inline citations in the format [1], [2], etc., matching the references list.
3. Identify one "primary_instrument" (e.g. an ETF, index fund, or related public company ticker) that gives retail investors logical exposure to this company's IPO or sector theme. Provide up to 2 "alternates".
4. If you cannot confidently identify a specific ticker, state the thematic exposure and set ticker to null. 
5. Add a short disclaimer.
6. The tone should be simple, objective, and retail-friendly.

Context Data:
{context_str}

Extract and format the response according to the strict JSON schema.
"""

            llm_with_structured_output = self._llm.with_structured_output(InvestorBrief)
            
            brief: InvestorBrief = await llm_with_structured_output.ainvoke(
                [SystemMessage(content=prompt)]
            )

            # Add explicit company_name if missing
            brief.company_name = company_name

            output_dict = brief.model_dump()
            await save_investor_brief(payload.analysis_id, output_dict)
            await log_agent_run_completed(run_id, output_reference=f"investor_brief populated")
            return output_dict
        except Exception as e:
            logger.error("InvestorBriefSynthesizer LLM call failed: %s", e)
            await log_agent_run_failed(run_id, error_message=str(e))
            return None
