import asyncio
import logging
from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel, Field

from backend.agents.complexity_classifier import ComplexityClassifierInput, classify_complexity
from backend.models.analysis import AnalysisComplexityTier
from backend.services.checkpoint_service import save_checkpoint

logger = logging.getLogger(__name__)


class LeadOrchestratorInput(BaseModel):
    analysis_id: str
    company_name: str
    has_s1_filed: bool = False
    media_coverage_score: int = 0
    source_count_hint: int = 0


class LeadPlan(BaseModel):
    analysis_id: str
    company_name: str
    complexity: AnalysisComplexityTier
    active_sources: list[str]
    subagent_tasks: list[str] = Field(default_factory=list)
    checkpoint: str = "planning_complete"
    planned_at: datetime


class LeadOrchestratorOutput(BaseModel):
    analysis_id: str


class SubagentRunner(Protocol):
    async def __call__(self, analysis_id: str) -> str:
        ...


class LeadOrchestrator:
    def __init__(
        self,
        data_harvester: SubagentRunner,
        prospectus_parser: SubagentRunner,
        scenario_builder: SubagentRunner,
        recommendation_engine: SubagentRunner,
    ) -> None:
        self._data_harvester = data_harvester
        self._prospectus_parser = prospectus_parser
        self._scenario_builder = scenario_builder
        self._recommendation_engine = recommendation_engine

    async def run(self, payload: LeadOrchestratorInput) -> LeadOrchestratorOutput:
        classifier_output = classify_complexity(
            ComplexityClassifierInput(
                company_name=payload.company_name,
                has_s1_filed=payload.has_s1_filed,
                media_coverage_score=payload.media_coverage_score,
                source_count_hint=payload.source_count_hint,
            )
        )

        plan = LeadPlan(
            analysis_id=payload.analysis_id,
            company_name=payload.company_name,
            complexity=classifier_output.complexity_tier,
            active_sources=classifier_output.active_sources,
            subagent_tasks=self._build_subagent_tasks(payload.company_name, classifier_output.complexity_tier),
            planned_at=datetime.now(timezone.utc),
        )

        await save_checkpoint(
            analysis_id=payload.analysis_id,
            agent_name="lead_orchestrator",
            checkpoint_data=plan.model_dump(mode="json"),
        )

        results = await asyncio.gather(
            self._data_harvester(payload.analysis_id),
            self._prospectus_parser(payload.analysis_id),
            self._scenario_builder(payload.analysis_id),
            self._recommendation_engine(payload.analysis_id),
            return_exceptions=True,
        )

        failures = [result for result in results if isinstance(result, Exception)]
        if failures:
            logger.error("Subagent execution failures for analysis_id=%s", payload.analysis_id)
            raise RuntimeError("One or more subagents failed")

        return LeadOrchestratorOutput(analysis_id=payload.analysis_id)

    def _build_subagent_tasks(
        self,
        company_name: str,
        complexity_tier: AnalysisComplexityTier,
    ) -> list[str]:
        return [
            f"Harvest IPO data for {company_name} at {complexity_tier} complexity.",
            f"Parse S-1 and extract structured facts for {company_name}.",
            f"Build pessimistic, realistic, and optimistic scenarios for {company_name}.",
            f"Generate ETF recommendations for each scenario for {company_name}.",
        ]
