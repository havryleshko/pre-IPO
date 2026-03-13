from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel

from backend.database.queries import (
    get_analysis_by_id,
    save_judge_output,
    set_flags_and_export_lock,
)
from backend.models.judge_output import JudgeFlag, JudgeOutput
from backend.services.agent_run_logger import (
    log_agent_run_completed,
    log_agent_run_failed,
    log_agent_run_start,
)


class JudgeAgentInput(BaseModel):
    analysis_id: str


class JudgeAgentResult(BaseModel):
    analysis_id: str


class RetryOnceHandler(Protocol):
    async def __call__(self, analysis_id: str, failing_sections: list[str]) -> bool: ...


class _ValidationIssue(BaseModel):
    section: str
    severity: str
    reason: str
    source_reference: str


class JudgeAgent:
    def __init__(self, retry_handler: RetryOnceHandler | None = None) -> None:
        self._retry_handler = retry_handler

    async def run(self, payload: JudgeAgentInput) -> JudgeAgentResult:
        run_record = await log_agent_run_start(
            analysis_id=payload.analysis_id,
            agent_name="judge_agent",
            input_reference=f"analysis_id={payload.analysis_id}",
        )
        run_id: str = str(run_record["id"]) if run_record else ""

        try:
            analysis = await get_analysis_by_id(payload.analysis_id)
            if analysis is None:
                raise RuntimeError(f"Analysis not found for analysis_id={payload.analysis_id}")

            issues = self._collect_issues(analysis)
            retry_attempted = False
            retry_passed = False

            if issues and self._retry_handler is not None:
                retry_attempted = True
                retry_passed = await self._retry_handler(payload.analysis_id, [item.section for item in issues])
                if retry_passed:
                    refreshed = await get_analysis_by_id(payload.analysis_id)
                    if refreshed is not None:
                        analysis = refreshed
                        issues = self._collect_issues(analysis)
                        retry_passed = len(issues) == 0
                    else:
                        retry_passed = False

            validation_passed = len(issues) == 0
            export_locked = not validation_passed
            ifa_confirmed_flags = self._extract_confirmed_flags(analysis.get("ifa_confirmed_flags"))

            flags: list[JudgeFlag] = []
            for item in issues:
                flags.append(
                    JudgeFlag(
                        flag_id=uuid4(),
                        section=item.section,
                        severity="red" if item.severity == "red" else "amber",
                        reason=item.reason,
                        source_reference=item.source_reference,
                        retry_attempted=retry_attempted,
                        retry_passed=retry_passed,
                        improvement_suggestion=self._improvement_suggestion(item.section, item.reason),
                    )
                )

            output = JudgeOutput(
                validation_passed=validation_passed,
                flags=flags,
                export_locked=export_locked,
                ifa_confirmed_flags=ifa_confirmed_flags,
                validated_at=datetime.now(timezone.utc),
            )
            await save_judge_output(
                analysis_id=payload.analysis_id,
                output=output.model_dump(mode="json"),
            )
            await set_flags_and_export_lock(
                analysis_id=payload.analysis_id,
                flags=[item.model_dump(mode="json") for item in flags],
                export_locked=export_locked,
            )
        except Exception as exc:
            await log_agent_run_failed(run_id=run_id, error_message=str(exc))
            raise

        await log_agent_run_completed(
            run_id=run_id,
            output_reference=f"analysis_id={payload.analysis_id}",
        )
        return JudgeAgentResult(analysis_id=payload.analysis_id)

    def _collect_issues(self, analysis: Any) -> list[_ValidationIssue]:
        parser_output = analysis.get("parser_output")
        scenario_output = analysis.get("scenario_output")
        recommendation_output = analysis.get("recommendation_output")
        harvester_output = analysis.get("harvester_output")

        parser = parser_output if isinstance(parser_output, dict) else {}
        scenario = scenario_output if isinstance(scenario_output, dict) else {}
        recommendation = recommendation_output if isinstance(recommendation_output, dict) else {}
        harvester = harvester_output if isinstance(harvester_output, dict) else {}

        issues: list[_ValidationIssue] = []

        if not parser or not scenario or not recommendation:
            issues.append(
                _ValidationIssue(
                    section="Pipeline Outputs",
                    severity="red",
                    reason="One or more required agent outputs are null or empty unexpectedly",
                    source_reference="analyses.parser_output / analyses.scenario_output / analyses.recommendation_output",
                )
            )

        scenarios = scenario.get("scenarios")
        scenarios_dict = scenarios if isinstance(scenarios, dict) else {}
        if not self._scenarios_complete(scenarios_dict):
            issues.append(
                _ValidationIssue(
                    section="Scenario Completeness",
                    severity="red",
                    reason="All three scenarios are not present and complete",
                    source_reference="scenario_output.scenarios",
                )
            )

        probability_sum = self._to_float(scenario.get("probability_sum_check"))
        if probability_sum is None or abs(probability_sum - 100.0) > 0.01:
            issues.append(
                _ValidationIssue(
                    section="Probability Sum",
                    severity="red",
                    reason="Scenario probabilities do not sum to exactly 100",
                    source_reference="scenario_output.probability_sum_check",
                )
            )

        risk_factors = parser.get("risk_factors")
        if isinstance(risk_factors, list):
            if any(not self._has_source_citation(str(item)) for item in risk_factors):
                issues.append(
                    _ValidationIssue(
                        section="Risk Factor Citations",
                        severity="amber",
                        reason="One or more risk factors appear without a named source citation",
                        source_reference="parser_output.risk_factors",
                    )
                )

        pre_ipo = recommendation.get("pre_ipo_beneficiary_funds")
        if not isinstance(pre_ipo, dict) or not self._pre_ipo_has_evidence(pre_ipo):
            issues.append(
                _ValidationIssue(
                    section="Pre-IPO Beneficiary Funds",
                    severity="amber",
                    reason="Pre-IPO beneficiary funds section is missing or lacks evidence",
                    source_reference="recommendation_output.pre_ipo_beneficiary_funds",
                )
            )

        recommendations = recommendation.get("recommendations")
        recommendations_dict = recommendations if isinstance(recommendations, dict) else {}
        if not self._positioning_present(recommendations_dict):
            issues.append(
                _ValidationIssue(
                    section="Post-IPO Positioning",
                    severity="red",
                    reason="Positioning recommendation is missing for one or more scenarios",
                    source_reference="recommendation_output.recommendations",
                )
            )
        if not self._risk_warning_present(recommendations_dict):
            issues.append(
                _ValidationIssue(
                    section="Risk Warnings",
                    severity="amber",
                    reason="Risk warning is missing for one or more scenarios",
                    source_reference="recommendation_output.recommendations.*.risk_warning",
                )
            )

        if not self._financial_metrics_sourced_or_flagged(parser):
            issues.append(
                _ValidationIssue(
                    section="Financial Metric Sourcing",
                    severity="amber",
                    reason="Financial metrics are missing without explicit parser flags",
                    source_reference="parser_output.financials / parser_output.flagged_sections",
                )
            )

        summary = str(recommendation.get("plain_english_summary") or "")
        if self._contains_legal_jargon(summary):
            issues.append(
                _ValidationIssue(
                    section="Plain-English Summary",
                    severity="amber",
                    reason="Summary contains legal jargon",
                    source_reference="recommendation_output.plain_english_summary",
                )
            )

        if not self._client_paragraph_limits(recommendations_dict):
            issues.append(
                _ValidationIssue(
                    section="Client Paragraph Length",
                    severity="amber",
                    reason="One or more client paragraphs exceed 500 words or are empty",
                    source_reference="recommendation_output.recommendations.*.client_paragraph",
                )
            )

        if not self._time_horizons_present(scenarios_dict):
            issues.append(
                _ValidationIssue(
                    section="Time Horizons",
                    severity="red",
                    reason="30d, 90d, and 1y price targets are missing for one or more scenarios",
                    source_reference="scenario_output.scenarios.*.price_targets",
                )
            )

        if not self._sentiment_present_or_flagged(harvester):
            issues.append(
                _ValidationIssue(
                    section="Sentiment Signal",
                    severity="amber",
                    reason="Twitter sentiment is missing and no source failure reason is present",
                    source_reference="harvester_output.twitter_data / harvester_output.sources_failed",
                )
            )

        if self._looks_hallucinated(recommendation, scenario):
            issues.append(
                _ValidationIssue(
                    section="Hallucination Guard",
                    severity="red",
                    reason="Detected placeholder or unsupported fields suggesting hallucinated output",
                    source_reference="recommendation_output / scenario_output",
                )
            )

        if not self._weighting_rationales_have_data(scenarios_dict):
            issues.append(
                _ValidationIssue(
                    section="Weighting Rationale",
                    severity="amber",
                    reason="Weighting rationale lacks specific data points for one or more scenarios",
                    source_reference="scenario_output.scenarios.*.weighting_rationale",
                )
            )

        return issues

    def _scenarios_complete(self, scenarios: dict[str, Any]) -> bool:
        required = ("pessimistic", "realistic", "optimistic")
        for name in required:
            payload = scenarios.get(name)
            if not isinstance(payload, dict):
                return False
            keys = ("probability", "drivers", "key_risks", "price_targets", "weighting_rationale", "rules_applied")
            if any(key not in payload for key in keys):
                return False
        return True

    def _has_source_citation(self, value: str) -> bool:
        text = value.lower()
        return ("source" in text) or ("sec" in text) or ("news" in text) or ("crunchbase" in text) or ("fred" in text)

    def _pre_ipo_has_evidence(self, pre_ipo: dict[str, Any]) -> bool:
        candidates = pre_ipo.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            return False
        for item in candidates:
            if not isinstance(item, dict):
                continue
            evidence = item.get("evidence")
            if isinstance(evidence, list) and any(str(entry).strip() for entry in evidence):
                return True
        return False

    def _positioning_present(self, recommendations: dict[str, Any]) -> bool:
        for name in ("pessimistic", "realistic", "optimistic"):
            item = recommendations.get(name)
            if not isinstance(item, dict):
                return False
            positioning = str(item.get("recommended_positioning") or "").strip()
            if not positioning:
                return False
        return True

    def _risk_warning_present(self, recommendations: dict[str, Any]) -> bool:
        for name in ("pessimistic", "realistic", "optimistic"):
            item = recommendations.get(name)
            if not isinstance(item, dict):
                return False
            warning = str(item.get("risk_warning") or "").strip()
            if not warning:
                return False
        return True

    def _financial_metrics_sourced_or_flagged(self, parser: dict[str, Any]) -> bool:
        financials = parser.get("financials")
        if not isinstance(financials, dict):
            return False
        revenue = financials.get("revenue")
        burn = financials.get("burn_rate_monthly")
        runway = financials.get("cash_runway_months")
        if revenue is not None and burn is not None and runway is not None:
            return True
        flagged = parser.get("flagged_sections")
        if not isinstance(flagged, list):
            return False
        flag_text = " ".join(str(item).lower() for item in flagged)
        return "financial" in flag_text

    def _contains_legal_jargon(self, value: str) -> bool:
        text = value.lower()
        banned = (
            "hereinafter",
            "aforementioned",
            "notwithstanding",
            "whereas",
            "pursuant",
            "indemnify",
            "warrant",
            "liability",
        )
        return any(token in text for token in banned)

    def _client_paragraph_limits(self, recommendations: dict[str, Any]) -> bool:
        for name in ("pessimistic", "realistic", "optimistic"):
            item = recommendations.get(name)
            if not isinstance(item, dict):
                return False
            text = str(item.get("client_paragraph") or "").strip()
            if not text:
                return False
            count = len([token for token in text.split() if token.strip()])
            if count > 500:
                return False
        return True

    def _time_horizons_present(self, scenarios: dict[str, Any]) -> bool:
        for name in ("pessimistic", "realistic", "optimistic"):
            item = scenarios.get(name)
            if not isinstance(item, dict):
                return False
            targets = item.get("price_targets")
            if not isinstance(targets, dict):
                return False
            if any(key not in targets for key in ("30_days", "90_days", "1_year")):
                return False
        return True

    def _sentiment_present_or_flagged(self, harvester: dict[str, Any]) -> bool:
        twitter = harvester.get("twitter_data")
        if isinstance(twitter, dict):
            sentiment = twitter.get("sentiment_score")
            if isinstance(sentiment, dict):
                keys = ("positive", "negative", "neutral")
                if all(key in sentiment for key in keys):
                    return True
        failed = harvester.get("sources_failed")
        if not isinstance(failed, list):
            return False
        return any(str(item).lower().find("twitter") >= 0 for item in failed)

    def _looks_hallucinated(self, recommendation: dict[str, Any], scenario: dict[str, Any]) -> bool:
        text = f"{recommendation} {scenario}".lower()
        bad_tokens = ("lorem ipsum", "tbd", "todo", "placeholder", "unknown unknown")
        return any(token in text for token in bad_tokens)

    def _weighting_rationales_have_data(self, scenarios: dict[str, Any]) -> bool:
        for name in ("pessimistic", "realistic", "optimistic"):
            item = scenarios.get(name)
            if not isinstance(item, dict):
                return False
            rationale = str(item.get("weighting_rationale") or "")
            has_number = any(char.isdigit() for char in rationale)
            has_source_like = any(term in rationale.lower() for term in ("source", "sec", "fred", "news", "crunchbase", "twitter"))
            if not (has_number and has_source_like):
                return False
        return True

    def _extract_confirmed_flags(self, raw: Any) -> list[UUID]:
        if not isinstance(raw, list):
            return []
        parsed: list[UUID] = []
        for item in raw:
            try:
                parsed.append(UUID(str(item)))
            except ValueError:
                continue
        return parsed

    def _improvement_suggestion(self, section: str, reason: str) -> str | None:
        text = f"{section} {reason}".lower()
        if "risk factor" in text:
            return "Require explicit source tagging for each risk factor sentence."
        if "weighting rationale" in text:
            return "Enforce rationale template with numeric evidence and named source."
        if "financial" in text:
            return "Add fallback extraction rules for alternative financial term variants."
        if "pre-ipo beneficiary funds" in text:
            return "Increase corroboration threshold using cross-source mention matching."
        return None

    def _to_float(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip().replace(",", "")
            if not text:
                return None
            try:
                return float(text)
            except ValueError:
                return None
        return None
