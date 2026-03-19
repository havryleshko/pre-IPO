import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel

from backend.database.queries import get_analysis_by_id, save_recommendation_output
from backend.models.recommendation_output import (
    BeneficiaryFundCandidate,
    PreIpoBeneficiaryFunds,
    RecommendationOutput,
    Recommendations,
    RetailActionIdeas,
    RetailSummary,
    ScenarioRecommendation,
)
from backend.services.agent_run_logger import (
    log_agent_run_completed,
    log_agent_run_failed,
    log_agent_run_start,
)


class RecommendationEngineInput(BaseModel):
    analysis_id: str


class RecommendationEngineResult(BaseModel):
    analysis_id: str


class RecommendationEngine:
    async def run(self, payload: RecommendationEngineInput) -> RecommendationEngineResult:
        run_record = await log_agent_run_start(
            analysis_id=payload.analysis_id,
            agent_name="recommendation_engine",
            input_reference=f"analysis_id={payload.analysis_id}",
        )
        run_id: str = str(run_record["id"]) if run_record else ""

        try:
            analysis = await get_analysis_by_id(payload.analysis_id)
            if analysis is None:
                raise RuntimeError(f"Analysis not found for analysis_id={payload.analysis_id}")

            company_name = str(analysis.get("company_name") or "unknown")
            scenario_output = analysis.get("scenario_output")
            parser_output = analysis.get("parser_output")
            harvester_output = analysis.get("harvester_output")
            if not isinstance(scenario_output, dict):
                scenario_output = {}
            if not isinstance(parser_output, dict):
                parser_output = {}
            if not isinstance(harvester_output, dict):
                harvester_output = {}

            recommendation_output = self._build_recommendation_output(
                company_name=company_name,
                scenario_output=scenario_output,
                parser_output=parser_output,
                harvester_output=harvester_output,
            )
            await save_recommendation_output(
                analysis_id=payload.analysis_id,
                output=recommendation_output.model_dump(mode="json"),
            )
        except Exception as exc:
            await log_agent_run_failed(run_id=run_id, error_message=str(exc))
            raise

        await log_agent_run_completed(
            run_id=run_id,
            output_reference=f"analysis_id={payload.analysis_id}",
        )
        return RecommendationEngineResult(analysis_id=payload.analysis_id)

    def _build_recommendation_output(
        self,
        company_name: str,
        scenario_output: dict[str, Any],
        parser_output: dict[str, Any],
        harvester_output: dict[str, Any],
    ) -> RecommendationOutput:
        scenarios = scenario_output.get("scenarios")
        scenarios_dict = scenarios if isinstance(scenarios, dict) else {}
        preliminary = self._is_preliminary(parser_output)
        tradability_ok = self._has_minimum_tradability_evidence(parser_output)
        decision = self._build_decision(
            preliminary=preliminary,
            scenarios_dict=scenarios_dict,
            parser_output=parser_output,
        )

        pessimistic = scenarios_dict.get("pessimistic")
        realistic = scenarios_dict.get("realistic")
        optimistic = scenarios_dict.get("optimistic")

        pessimistic_reco = self._build_scenario_recommendation(
            scenario_name="pessimistic",
            scenario_data=pessimistic if isinstance(pessimistic, dict) else {},
            company_name=company_name,
            parser_output=parser_output,
            preliminary=preliminary,
        )
        realistic_reco = self._build_scenario_recommendation(
            scenario_name="realistic",
            scenario_data=realistic if isinstance(realistic, dict) else {},
            company_name=company_name,
            parser_output=parser_output,
            preliminary=preliminary,
        )
        optimistic_reco = self._build_scenario_recommendation(
            scenario_name="optimistic",
            scenario_data=optimistic if isinstance(optimistic, dict) else {},
            company_name=company_name,
            parser_output=parser_output,
            preliminary=preliminary,
        )
        pre_ipo_funds = self._build_pre_ipo_beneficiary_funds(company_name, parser_output, harvester_output)

        funds_to_consider = self._build_funds_to_consider(pre_ipo_funds)
        decision_scope = self._build_decision_scope(
            decision=decision,
            preliminary=preliminary,
            tradability_ok=tradability_ok,
            has_pre_ipo_funds=len(funds_to_consider) > 0,
        )
        investment_action = self._build_investment_action(
            company_name=company_name,
            pre_ipo_funds=pre_ipo_funds,
            realistic_reco=realistic_reco,
            preliminary=preliminary,
            decision=decision,
            decision_scope=decision_scope,
        )
        entry_triggers = self._build_entry_triggers(
            decision=decision,
            decision_scope=decision_scope,
            parser_output=parser_output,
            scenarios_dict=scenarios_dict,
            harvester_output=harvester_output,
            funds_to_consider=funds_to_consider,
        )
        watch_triggers = self._build_watch_triggers(
            decision=decision,
            preliminary=preliminary,
            parser_output=parser_output,
            scenarios_dict=scenarios_dict,
            harvester_output=harvester_output,
        )
        kill_criteria = self._build_kill_criteria(
            decision=decision,
            preliminary=preliminary,
            tradability_ok=tradability_ok,
            parser_output=parser_output,
            scenarios_dict=scenarios_dict,
            decision_scope=decision_scope,
        )
        what_to_watch = self._build_what_to_watch(
            parser_output=parser_output,
            scenarios_dict=scenarios_dict,
            harvester_output=harvester_output,
        )
        decision_evidence = self._build_decision_evidence(
            parser_output=parser_output,
            harvester_output=harvester_output,
        )
        decision_rationale = self._build_decision_rationale(
            decision=decision,
            decision_scope=decision_scope,
            decision_evidence=decision_evidence,
            entry_triggers=entry_triggers,
            watch_triggers=watch_triggers,
            kill_criteria=kill_criteria,
        )
        summary = self._plain_english_summary(
            company_name=company_name,
            pre_ipo_funds=pre_ipo_funds,
            pessimistic=pessimistic_reco,
            realistic=realistic_reco,
            optimistic=optimistic_reco,
            scenarios_dict=scenarios_dict,
            parser_output=parser_output,
            harvester_output=harvester_output,
            decision=decision,
            decision_scope=decision_scope,
            entry_triggers=entry_triggers,
            watch_triggers=watch_triggers,
            kill_criteria=kill_criteria,
            decision_evidence=decision_evidence,
        )
        retail_summary = self._build_retail_summary(
            company_name=company_name,
            parser_output=parser_output,
            scenarios_dict=scenarios_dict,
            decision=decision,
            decision_scope=decision_scope,
            realistic_reco=realistic_reco,
            pre_ipo_funds=pre_ipo_funds,
            entry_triggers=entry_triggers,
            watch_triggers=watch_triggers,
            kill_criteria=kill_criteria,
            preliminary=preliminary,
        )

        return RecommendationOutput(
            company_name=company_name,
            decision=decision,
            decision_scope=decision_scope,
            entry_triggers=entry_triggers,
            watch_triggers=watch_triggers,
            decision_rationale=decision_rationale,
            decision_evidence=decision_evidence,
            kill_criteria=kill_criteria,
            pre_ipo_beneficiary_funds=pre_ipo_funds,
            recommendations=Recommendations(
                pessimistic=pessimistic_reco,
                realistic=realistic_reco,
                optimistic=optimistic_reco,
            ),
            plain_english_summary=summary,
            investment_action=investment_action,
            funds_to_consider=funds_to_consider,
            what_to_watch=what_to_watch,
            retail_summary=retail_summary,
            generated_at=datetime.now(timezone.utc),
        )

    def _build_decision(
        self,
        preliminary: bool,
        scenarios_dict: dict[str, Any],
        parser_output: dict[str, Any],
    ) -> Literal["buy", "watch", "avoid"]:
        if preliminary:
            return "watch"

        if not self._has_minimum_tradability_evidence(parser_output):
            return "watch"

        pessimistic_p = self._scenario_probability(scenarios_dict, "pessimistic")
        realistic_p = self._scenario_probability(scenarios_dict, "realistic")
        optimistic_p = self._scenario_probability(scenarios_dict, "optimistic")

        if optimistic_p >= pessimistic_p and optimistic_p >= realistic_p:
            return "buy"
        if pessimistic_p >= optimistic_p and pessimistic_p >= realistic_p:
            return "avoid"
        return "watch"

    def _build_decision_scope(
        self,
        decision: Literal["buy", "watch", "avoid"],
        preliminary: bool,
        tradability_ok: bool,
        has_pre_ipo_funds: bool,
    ) -> Literal["pre_ipo_fund", "post_ipo_direct", "no_trade"]:
        if decision == "avoid":
            return "no_trade"

        if preliminary or not tradability_ok:
            return "no_trade"

        if decision == "buy":
            return "pre_ipo_fund" if has_pre_ipo_funds else "post_ipo_direct"

        return "post_ipo_direct"

    def _build_entry_triggers(
        self,
        decision: Literal["buy", "watch", "avoid"],
        decision_scope: Literal["pre_ipo_fund", "post_ipo_direct", "no_trade"],
        parser_output: dict[str, Any],
        scenarios_dict: dict[str, Any],
        harvester_output: dict[str, Any],
        funds_to_consider: list[str],
    ) -> list[str]:
        if decision != "buy":
            return []

        probs: dict[str, float] = {
            "pessimistic": self._scenario_probability(scenarios_dict, "pessimistic"),
            "realistic": self._scenario_probability(scenarios_dict, "realistic"),
            "optimistic": self._scenario_probability(scenarios_dict, "optimistic"),
        }
        entry_scenario = max(probs, key=lambda scenario_name: probs[scenario_name]) if probs else "optimistic"
        entry_prob = probs.get(entry_scenario, 0.0)

        scenario_payload = scenarios_dict.get(entry_scenario) if isinstance(scenarios_dict, dict) else {}
        drivers = scenario_payload.get("drivers") if isinstance(scenario_payload, dict) else []
        driver_text = str(drivers[0]) if isinstance(drivers, list) and drivers else "available scenario inputs"

        lockup_days = self._to_float(parser_output.get("lockup_period_days"))
        offering_type = str(parser_output.get("offering_type") or "primary").lower()

        triggers: list[str] = [
            f"Entry thesis: {entry_scenario} outlook at {round(entry_prob, 2)}% probability, driven by {driver_text[:140]}.",
            f"Offering structure: {offering_type} offering mechanics noted; confirm terms before entry.",
        ]

        if lockup_days is not None and lockup_days > 0:
            triggers.append(f"Lock-up expiry: {int(lockup_days)} days after listing (insider/lock-up terms verified).")

        demand_signals = parser_output.get("demand_signals") if isinstance(parser_output.get("demand_signals"), dict) else None
        if isinstance(demand_signals, dict):
            roadshow = str(demand_signals.get("roadshow_sentiment") or "").strip()
            if roadshow:
                triggers.append(f"Demand signal: roadshow sentiment indicates '{roadshow[:120]}'.")

        financials = parser_output.get("financials") if isinstance(parser_output.get("financials"), dict) else {}
        if isinstance(financials, dict):
            revenue = self._to_float(financials.get("revenue"))
            burn = self._to_float(financials.get("burn_rate_monthly"))
            if revenue is not None and revenue > 0:
                triggers.append(f"Financial baseline: revenue {self._fmt_money(revenue)} extracted from filing/metrics.")
            if burn is not None and burn > 0:
                triggers.append(f"Operational burn: {self._fmt_money(burn)}/month captured for sizing context.")

        fred = harvester_output.get("fred_data") if isinstance(harvester_output.get("fred_data"), dict) else {}
        if isinstance(fred, dict):
            macro = str(fred.get("market_conditions") or "").strip()
            if macro:
                triggers.append(f"Macro backdrop: {macro[:140]} (cross-check with FRED snapshot).")

        if decision_scope == "pre_ipo_fund" and funds_to_consider:
            triggers.append(f"Initial vehicle: {funds_to_consider[0]} selected for pre-IPO exposure; keep allocation flexible.")

        flagged = parser_output.get("flagged_sections")
        if isinstance(flagged, list) and flagged:
            sections = [
                str(item.get("section", ""))
                for item in flagged[:3]
                if isinstance(item, dict) and str(item.get("section", "")).strip()
            ]
            if sections:
                triggers.append(f"Entry gating: resolve flagged filing sections: {', '.join(sections)}.")

        return triggers[:6]

    def _build_watch_triggers(
        self,
        decision: Literal["buy", "watch", "avoid"],
        preliminary: bool,
        parser_output: dict[str, Any],
        scenarios_dict: dict[str, Any],
        harvester_output: dict[str, Any],
    ) -> list[str]:
        if decision == "buy":
            return []

        triggers: list[str] = []

        if preliminary:
            triggers.append("Evidence quality is low; confirm financials, offering mechanics, and demand signals before acting.")

        flagged = parser_output.get("flagged_sections")
        if isinstance(flagged, list) and flagged:
            sections = [
                str(item.get("section", ""))
                for item in flagged[:3]
                if isinstance(item, dict) and str(item.get("section", "")).strip()
            ]
            if sections:
                triggers.append(f"Verify flagged sections: {', '.join(sections)}")

        financials = parser_output.get("financials") if isinstance(parser_output.get("financials"), dict) else {}
        if isinstance(financials, dict):
            revenue = financials.get("revenue")
            revenue_evidence = financials.get("revenue_evidence")
            if revenue is None:
                triggers.append("Confirm revenue extraction from SEC financial statements.")
            elif revenue_evidence is None:
                triggers.append("Confirm revenue evidence link (audited figures) for sizing context.")

            burn_rate = financials.get("burn_rate_monthly")
            burn_evidence = financials.get("burn_rate_monthly_evidence")
            if burn_rate is None:
                triggers.append("Confirm burn rate / cash used per month extraction.")
            elif burn_evidence is None:
                triggers.append("Confirm burn-rate evidence link for underwriting assumptions.")

            runway = financials.get("cash_runway_months")
            runway_evidence = financials.get("cash_runway_months_evidence")
            if runway is None:
                triggers.append("Confirm cash runway months extraction (liquidity view).")
            elif runway_evidence is None:
                triggers.append("Confirm runway evidence link for monitoring posture.")

        if (
            "use_of_proceeds_evidence" in parser_output
            and parser_output.get("use_of_proceeds_evidence") is None
            and parser_output.get("use_of_proceeds") is not None
        ):
            triggers.append("Verify use-of-proceeds evidence from the S-1 record.")

        risk_factors_evidence = parser_output.get("risk_factors_evidence")
        if (
            "risk_factors" in parser_output
            and isinstance(parser_output.get("risk_factors"), list)
            and parser_output.get("risk_factors_evidence") == []
            and isinstance(risk_factors_evidence, list)
        ):
            triggers.append("Verify structured risk-factor sources (TOC noise filtered) for each risk bucket.")

        follow_up = self._build_what_to_watch(
            parser_output=parser_output,
            scenarios_dict=scenarios_dict,
            harvester_output=harvester_output,
        )

        for item in follow_up:
            if item not in triggers:
                triggers.append(item)
            if len(triggers) >= 6:
                break

        if not triggers:
            triggers = follow_up[:6]

        return triggers[:6]

    def _build_kill_criteria(
        self,
        decision: Literal["buy", "watch", "avoid"],
        preliminary: bool,
        tradability_ok: bool,
        parser_output: dict[str, Any],
        scenarios_dict: dict[str, Any],
        decision_scope: Literal["pre_ipo_fund", "post_ipo_direct", "no_trade"],
    ) -> list[str]:
        triggers: list[str] = []

        if decision == "avoid":
            triggers.append("Kill: recommendation is avoid (downside outweighs base/upside signals).")

        if preliminary:
            triggers.append("Kill: parser confidence/evidence quality is low; do not proceed until verified.")

        if not tradability_ok:
            triggers.append("Kill: tradability evidence fails validation (public float/lock-up not defensible).")

        flagged = parser_output.get("flagged_sections")
        if isinstance(flagged, list) and flagged:
            sections = [
                str(item.get("section", ""))
                for item in flagged[:4]
                if isinstance(item, dict) and str(item.get("section", "")).strip()
            ]
            if sections:
                triggers.append(f"Kill: unresolved flagged SEC sections: {', '.join(sections)}")

        financials = parser_output.get("financials") if isinstance(parser_output.get("financials"), dict) else {}
        if isinstance(financials, dict) and financials:
            revenue = financials.get("revenue")
            burn = financials.get("burn_rate_monthly")
            runway = financials.get("cash_runway_months")
            if revenue is None:
                triggers.append("Kill: revenue remains unverified for underwriting context.")
            if burn is None:
                triggers.append("Kill: monthly burn/cash-used extraction is missing.")
            if runway is None:
                triggers.append("Kill: cash runway months extraction is missing.")

        risk_factors_evidence = parser_output.get("risk_factors_evidence")
        risk_factors = parser_output.get("risk_factors")
        if (
            "risk_factors" in parser_output
            and isinstance(risk_factors, list)
            and isinstance(risk_factors_evidence, list)
            and risk_factors
            and risk_factors_evidence == []
        ):
            triggers.append("Kill: risk-factor citations absent after TOC noise filtering.")

        if (
            "use_of_proceeds_evidence" in parser_output
            and parser_output.get("use_of_proceeds_evidence") is None
            and parser_output.get("use_of_proceeds") is not None
        ):
            triggers.append("Kill: use-of-proceeds evidence link missing from filing record.")

        pessimistic = scenarios_dict.get("pessimistic") if isinstance(scenarios_dict, dict) else {}
        if isinstance(pessimistic, dict):
            pessimistic_p = self._to_float(pessimistic.get("probability")) or 0.0
            kr = pessimistic.get("key_risks")
            if isinstance(kr, list) and kr:
                primary = str(kr[0])
                if self._RISK_NOISE.search(primary):
                    primary = "market volatility and execution risk"
                triggers.append(
                    f"Kill: downside materializes if '{primary[:120]}' worsens post-filing."
                )
            elif pessimistic_p >= 50:
                triggers.append("Kill: pessimistic scenario probability remains dominant (>={}%); reassess thesis.".format(int(round(pessimistic_p))))

        if decision_scope == "pre_ipo_fund":
            triggers.append("Kill: pre-IPO fund thesis should be dropped if vehicle corroboration weakens or evidence updates reverse.")

        deduped: list[str] = []
        seen: set[str] = set()
        for item in triggers:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
            if len(deduped) >= 6:
                break

        return deduped

    def _build_decision_evidence(
        self,
        parser_output: dict[str, Any],
        harvester_output: dict[str, Any],
    ) -> list[str]:
        evidence: list[str] = []

        if not isinstance(parser_output, dict):
            parser_output = {}
        if not isinstance(harvester_output, dict):
            harvester_output = {}

        data_confidence = parser_output.get("data_confidence")
        if data_confidence is not None:
            evidence.append(f"parser:data_confidence={str(data_confidence).lower()}")

        offering_type = parser_output.get("offering_type")
        if offering_type is not None:
            evidence.append(f"parser:offering_type={str(offering_type).lower()}")

        lockup_days = self._to_float(parser_output.get("lockup_period_days"))
        if lockup_days is not None:
            evidence.append(f"parser:lockup_period_days={int(lockup_days)}")

        float_details = parser_output.get("float_details")
        if isinstance(float_details, dict):
            public_float = self._to_float(float_details.get("public_float"))
            if public_float is not None:
                evidence.append(f"parser:float_details.public_float={int(public_float)}")
            total_shares = self._to_float(float_details.get("total_shares_offered"))
            if total_shares is not None:
                evidence.append(f"parser:float_details.total_shares_offered={int(total_shares)}")

        financials = parser_output.get("financials") if isinstance(parser_output.get("financials"), dict) else {}
        if financials:
            revenue = self._to_float(financials.get("revenue"))
            if revenue is not None:
                evidence.append(f"parser:financials.revenue={int(revenue)}")

            burn = self._to_float(financials.get("burn_rate_monthly"))
            if burn is not None:
                evidence.append(f"parser:financials.burn_rate_monthly={int(burn)}")

            runway = self._to_float(financials.get("cash_runway_months"))
            if runway is not None:
                evidence.append(f"parser:financials.cash_runway_months={int(runway)}")

        flagged_sections = parser_output.get("flagged_sections")
        if isinstance(flagged_sections, list) and flagged_sections:
            for item in flagged_sections[:3]:
                if not isinstance(item, dict):
                    continue
                section = str(item.get("section") or "").strip()
                reason = str(item.get("reason") or "").strip()
                verify_at = str(item.get("verify_at") or "").strip()
                if section or reason:
                    evidence.append(
                        "parser:flagged_sections="
                        + ",".join(
                            part
                            for part in (
                                f"section={section}" if section else "",
                                f"reason={reason}" if reason else "",
                                f"verify_at={verify_at}" if verify_at else "",
                            )
                            if part
                        )
                    )

        for key in (
            "revenue_evidence",
            "burn_rate_monthly_evidence",
            "cash_runway_months_evidence",
            "risk_factors_evidence",
            "use_of_proceeds_evidence",
        ):
            value = financials.get(key) if isinstance(financials, dict) else None
            if isinstance(financials, dict) and value is None and key in financials:
                evidence.append(f"parser:{key}=null")
            elif value is not None:
                evidence.append(f"parser:{key}=present")

        if "risk_factors_evidence" in parser_output:
            rf_evidence = parser_output.get("risk_factors_evidence")
            if rf_evidence is None:
                evidence.append("parser:risk_factors_evidence=null")
            else:
                evidence.append("parser:risk_factors_evidence=present")

        if "use_of_proceeds_evidence" in parser_output:
            up_evidence = parser_output.get("use_of_proceeds_evidence")
            if up_evidence is None:
                evidence.append("parser:use_of_proceeds_evidence=null")
            else:
                evidence.append("parser:use_of_proceeds_evidence=present")

        sources_active = harvester_output.get("sources_active")
        if isinstance(sources_active, list) and sources_active:
            evidence.append(f"harvester:sources_active={','.join(str(s).lower() for s in sources_active)}")

        sec_filings = harvester_output.get("sec_filings")
        if isinstance(sec_filings, list):
            evidence.append(f"harvester:sec_filings_count={len(sec_filings)}")

        news_articles = harvester_output.get("news_articles")
        if isinstance(news_articles, list):
            evidence.append(f"harvester:news_articles_count={len(news_articles)}")

        fred_data = harvester_output.get("fred_data")
        if isinstance(fred_data, dict):
            macro = str(fred_data.get("market_conditions") or "").strip()
            if macro:
                evidence.append(f"harvester:fred_data.market_conditions={macro.lower()}")

        twitter_data = harvester_output.get("twitter_data")
        if isinstance(twitter_data, dict):
            sentiment = twitter_data.get("sentiment_score")
            if isinstance(sentiment, dict):
                pos = self._to_float(sentiment.get("positive"))
                neg = self._to_float(sentiment.get("negative"))
                if pos is not None and neg is not None:
                    evidence.append(f"harvester:twitter.sentiment_positive={pos:.3f}")
                    evidence.append(f"harvester:twitter.sentiment_negative={neg:.3f}")

        deduped: list[str] = []
        seen: set[str] = set()
        for item in evidence:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
            if len(deduped) >= 12:
                break

        if not deduped:
            deduped = ["parser:insufficient_structured_evidence"]

        return deduped

    def _build_decision_rationale(
        self,
        decision: Literal["buy", "watch", "avoid"],
        decision_scope: Literal["pre_ipo_fund", "post_ipo_direct", "no_trade"],
        decision_evidence: list[str],
        entry_triggers: list[str],
        watch_triggers: list[str],
        kill_criteria: list[str],
    ) -> str:
        evidence_head = decision_evidence[0] if decision_evidence else "available market and filing evidence"
        if decision == "buy":
            trigger_text = entry_triggers[0] if entry_triggers else "confirm entry conditions before sizing"
            kill_text = kill_criteria[0] if kill_criteria else "reassess if downside risks increase"
            return (
                f"Buy posture with {decision_scope.replace('_', ' ')} scope based on {evidence_head}. "
                f"Entry focus: {trigger_text} Risk control: {kill_text}"
            )
        if decision == "watch":
            trigger_text = watch_triggers[0] if watch_triggers else "wait for stronger evidence before entry"
            kill_text = kill_criteria[0] if kill_criteria else "stay out until conditions improve"
            return (
                f"Watch posture with {decision_scope.replace('_', ' ')} scope because evidence is not strong enough yet. "
                f"Monitor: {trigger_text} Risk guard: {kill_text}"
            )
        kill_text = kill_criteria[0] if kill_criteria else "no-trade posture remains in force"
        return (
            f"Avoid posture with {decision_scope.replace('_', ' ')} scope due to downside risk and weak setup quality. "
            f"Stay out while {kill_text}"
        )

    def _build_scenario_recommendation(
        self,
        scenario_name: str,
        scenario_data: dict[str, Any],
        company_name: str,
        parser_output: dict[str, Any],
        preliminary: bool,
    ) -> ScenarioRecommendation:
        positioning = self._positioning_for_scenario(scenario_name, scenario_data, parser_output)
        conviction = self._conviction_for_scenario(scenario_data)
        probability = self._to_float(scenario_data.get("probability")) or 0.0
        drivers = scenario_data.get("drivers") if isinstance(scenario_data.get("drivers"), list) else []
        top_driver = str(drivers[0]) if drivers else "the available scenario inputs"

        if preliminary:
            rationale = self._preliminary_rationale(
                positioning=positioning,
                parser_output=parser_output,
                top_driver=top_driver,
            )
        else:
            rationale = (
                f"Selected {positioning.lower()} because {scenario_name} conditions are weighted at {round(probability, 2)}% "
                f"and driven by {top_driver[:140]} with {conviction.lower()} conviction."
            )
        risk_warning = self._risk_warning(scenario_name, scenario_data, parser_output)
        paragraph = (
            self._preliminary_client_paragraph(
                company_name=company_name,
                scenario_name=scenario_name,
                positioning=positioning,
                conviction=conviction,
                rationale=rationale,
                risk_warning=risk_warning,
                parser_output=parser_output,
            )
            if preliminary
            else self._client_paragraph(
                company_name=company_name,
                scenario_name=scenario_name,
                positioning=positioning,
                conviction=conviction,
                rationale=rationale,
                risk_warning=risk_warning,
                scenario_data=scenario_data,
                parser_output=parser_output,
            )
        )
        return ScenarioRecommendation(
            recommended_positioning=positioning,
            conviction=conviction,
            rationale=rationale,
            risk_warning=risk_warning,
            client_paragraph=paragraph,
        )

    def _positioning_for_scenario(
        self,
        scenario_name: str,
        scenario_data: dict[str, Any],
        parser_output: dict[str, Any],
    ) -> str:
        raw_drivers = scenario_data.get("drivers")
        drivers: list[Any] = raw_drivers if isinstance(raw_drivers, list) else []
        driver_text = " ".join(str(item).lower() for item in drivers)
        confidence = str(parser_output.get("data_confidence") or "medium").lower()

        if scenario_name == "pessimistic":
            return "capital preservation with low-volatility bias and staged entry"
        if scenario_name == "optimistic":
            if "macro: restrictive" in driver_text or confidence == "low":
                return "selective growth exposure with strict risk limits"
            return "growth-forward positioning with tactical upside participation"
        if "macro: restrictive" in driver_text:
            return "balanced positioning tilted toward quality and liquidity"
        return "balanced market exposure with incremental adds on confirmation"

    def _conviction_for_scenario(self, scenario_data: dict[str, Any]) -> str:
        probability = self._to_float(scenario_data.get("probability")) or 0.0
        if probability >= 50:
            return "high"
        if probability >= 30:
            return "medium"
        return "low"

    _RISK_NOISE = re.compile(r"investing in our .+ involves risks", re.IGNORECASE)

    def _risk_warning(self, scenario_name: str, scenario_data: dict[str, Any], parser_output: dict[str, Any]) -> str:
        risks = scenario_data.get("key_risks") if isinstance(scenario_data.get("key_risks"), list) else []
        primary = str(risks[0]) if risks else "market volatility and execution risk"
        if self._RISK_NOISE.search(primary):
            primary = "market volatility and execution risk"
        offering_type = str(parser_output.get("offering_type") or "primary")
        if scenario_name == "pessimistic":
            return (
                f"Downside risk remains elevated due to {primary[:160]} and potential post-listing pressure in a {offering_type} setup."
            )
        if scenario_name == "optimistic":
            return (
                f"Upside case can still unwind quickly if demand weakens or if {primary[:140]} materializes after listing."
            )
        return f"Base-case outcomes can deviate if {primary[:150]} worsens or macro conditions tighten further."

    def _client_paragraph(
        self,
        company_name: str,
        scenario_name: str,
        positioning: str,
        conviction: str,
        rationale: str,
        risk_warning: str,
        scenario_data: dict[str, Any],
        parser_output: dict[str, Any],
    ) -> str:
        probability = self._to_float(scenario_data.get("probability")) or 0.0
        raw_targets = scenario_data.get("price_targets")
        targets: dict[str, Any] = raw_targets if isinstance(raw_targets, dict) else {}
        p30 = self._to_float(targets.get("30_days"))
        p90 = self._to_float(targets.get("90_days"))
        p1y = self._to_float(targets.get("1_year"))
        raw_financials = parser_output.get("financials")
        financials: dict[str, Any] = raw_financials if isinstance(raw_financials, dict) else {}
        revenue = self._to_float(financials.get("revenue"))
        burn = self._to_float(financials.get("burn_rate_monthly"))
        confidence = str(parser_output.get("data_confidence") or "unknown")

        paragraph = (
            f"For the {scenario_name} case on {company_name}, our recommendation is {positioning}. This scenario currently carries "
            f"an estimated probability of {round(probability, 2)}%, and the projected path for the underlying setup points to "
            f"30-day / 90-day / 1-year reference levels of {self._fmt(p30)} / {self._fmt(p90)} / {self._fmt(p1y)}. "
            f"The recommendation is grounded in the scenario drivers and risk stack captured by the upstream analysis pipeline. "
            f"{rationale} Current parser confidence is {confidence}, with reported revenue at {self._fmt_money(revenue)} and burn dynamics "
            f"around {self._fmt_money(burn)} where available. The key idea for clients is not to express a single binary view on the IPO, "
            f"but to size exposure based on conviction ({conviction}) while preserving flexibility as new filing updates, demand signals, "
            f"and macro conditions arrive. "
            f"{risk_warning} Position sizing should remain consistent with the client risk profile, and this scenario should be revisited if "
            f"probability weights or key risk indicators change materially."
        )
        return paragraph

    def _plain_english_summary(
        self,
        company_name: str,
        pre_ipo_funds: PreIpoBeneficiaryFunds,
        pessimistic: ScenarioRecommendation,
        realistic: ScenarioRecommendation,
        optimistic: ScenarioRecommendation,
        scenarios_dict: dict[str, Any],
        parser_output: dict[str, Any],
        harvester_output: dict[str, Any],
        decision: Literal["buy", "watch", "avoid"],
        decision_scope: Literal["pre_ipo_fund", "post_ipo_direct", "no_trade"],
        entry_triggers: list[str],
        watch_triggers: list[str],
        kill_criteria: list[str],
        decision_evidence: list[str],
    ) -> str:
        if self._is_preliminary(parser_output):
            flagged_sections = parser_output.get("flagged_sections")
            flagged_count = len(flagged_sections) if isinstance(flagged_sections, list) else 0
            active_sources = harvester_output.get("sources_active")
            source_count = len(active_sources) if isinstance(active_sources, list) else 0
            funds_note = (
                "No defensible public fund beneficiary was identified yet."
                if not pre_ipo_funds.candidates
                else f"Current public-fund lead: {pre_ipo_funds.candidates[0].fund_name}."
            )
            return (
                f"Preliminary recommendation for {company_name}: decision={decision} scope={decision_scope}. "
                f"Current evidence is low confidence, with {flagged_count} material filing gaps and {source_count} active source checks completed. "
                f"{funds_note} Treat this as a monitored posture until financial, float, and demand evidence are verified."
            )

        p = self._scenario_probability(scenarios_dict, "pessimistic")
        r = self._scenario_probability(scenarios_dict, "realistic")
        o = self._scenario_probability(scenarios_dict, "optimistic")
        top_funds = ", ".join(item.fund_name for item in pre_ipo_funds.candidates[:3])
        pre_ipo_block = top_funds if top_funds else "no high-confidence pre-IPO beneficiary funds were identified"

        evidence_head = ", ".join(decision_evidence[:3]) if decision_evidence else ""
        entry_head = entry_triggers[0] if entry_triggers else ""
        watch_head = watch_triggers[0] if watch_triggers else ""
        kill_head = kill_criteria[0] if kill_criteria else ""

        decision_anchor = (
            f"Structured decision: {decision} ({decision_scope})."
            + (f" Evidence: {evidence_head}." if evidence_head else "")
        )

        guard = ""
        if decision == "buy" and entry_head:
            guard = f" Entry trigger example: {entry_head}"
        elif decision != "buy" and watch_head:
            guard = f" Monitoring trigger example: {watch_head}"
        if kill_head:
            guard = f"{guard} Kill criteria example: {kill_head}" if guard else f" Kill criteria example: {kill_head}"

        return (
            f"For {company_name}, pre-IPO beneficiary analysis points to {pre_ipo_block}. {decision_anchor}"
            f" For post-IPO positioning, we map downside ({round(p, 2)}%), base ({round(r, 2)}%), and upside ({round(o, 2)}%) paths to "
            f"{pessimistic.recommended_positioning}; {realistic.recommended_positioning}; and {optimistic.recommended_positioning}, "
            f"so clients can align exposure to changing conviction while separating private-exposure thesis from listing-outcome thesis.{guard}"
        )

    def _build_retail_summary(
        self,
        company_name: str,
        parser_output: dict[str, Any],
        scenarios_dict: dict[str, Any],
        decision: Literal["buy", "watch", "avoid"],
        decision_scope: Literal["pre_ipo_fund", "post_ipo_direct", "no_trade"],
        realistic_reco: ScenarioRecommendation,
        pre_ipo_funds: PreIpoBeneficiaryFunds,
        entry_triggers: list[str],
        watch_triggers: list[str],
        kill_criteria: list[str],
        preliminary: bool,
    ) -> RetailSummary:
        financials_raw = parser_output.get("financials")
        financials = financials_raw if isinstance(financials_raw, dict) else {}
        revenue = self._to_float(financials.get("revenue"))
        burn = self._to_float(financials.get("burn_rate_monthly"))
        runway = self._to_float(financials.get("cash_runway_months"))
        confidence = str(parser_output.get("data_confidence") or "unknown").lower()

        p = self._scenario_probability(scenarios_dict, "pessimistic")
        r = self._scenario_probability(scenarios_dict, "realistic")
        o = self._scenario_probability(scenarios_dict, "optimistic")

        direction = "has upside" if decision == "buy" else "needs more confirmation" if decision == "watch" else "faces downside risk"
        verdict = f"{company_name} likely {direction} over 12+ months based on current filing and market evidence."
        if preliminary:
            verdict = f"{company_name} is preliminary right now; use a watch posture until filing evidence improves."

        what_i_see_now = [
            f"Decision: {decision.upper()} ({decision_scope.replace('_', ' ')})",
            f"Data confidence: {confidence}",
            f"Base scenario probability: {round(r, 2)}% (upside {round(o, 2)}%, downside {round(p, 2)}%)",
        ]

        why_that_matters = [
            realistic_reco.rationale,
            "Scenarios define how much upside and downside risk is currently priced into the stance.",
        ]
        if preliminary:
            why_that_matters = [
                "Core evidence is incomplete, so this is a monitoring view and not a full conviction call.",
                "New SEC filing evidence can materially change the recommendation.",
            ]

        the_good: list[str] = []
        if revenue is not None:
            the_good.append(f"Revenue baseline is available at {self._fmt_money(revenue)}.")
        if runway is not None:
            the_good.append(f"Cash runway estimate is {self._fmt(runway)} months.")
        if pre_ipo_funds.candidates:
            the_good.append(f"Public exposure candidate identified: {pre_ipo_funds.candidates[0].fund_name}.")
        if not the_good:
            the_good.append("Scenario structure is available and supports disciplined monitoring.")

        the_risk: list[str] = []
        if burn is not None:
            the_risk.append(f"Monthly burn is around {self._fmt_money(burn)}, which can pressure execution.")
        if kill_criteria:
            the_risk.append(kill_criteria[0])
        if preliminary:
            the_risk.append("Key filing sections still need verification before any position sizing.")
        if not the_risk:
            the_risk.append("Execution and macro conditions can shift the setup quickly.")

        if decision == "buy":
            simple_conclusion = f"{company_name} is a buy with staged sizing and active risk controls."
        elif decision == "avoid":
            simple_conclusion = f"{company_name} is an avoid until downside risk and evidence quality improve."
        else:
            simple_conclusion = f"{company_name} stays on watch until evidence quality and tradability signals improve."

        key_data_points: list[str] = [
            f"Pessimistic / Realistic / Optimistic probabilities: {round(p, 2)}% / {round(r, 2)}% / {round(o, 2)}%",
            f"Data confidence: {confidence}",
        ]
        if revenue is not None:
            key_data_points.append(f"Revenue: {self._fmt_money(revenue)}")
        if burn is not None:
            key_data_points.append(f"Burn rate: {self._fmt_money(burn)} per month")
        if runway is not None:
            key_data_points.append(f"Cash runway: {self._fmt(runway)} months")

        conservative = (
            f"Take no position yet and monitor: {watch_triggers[0]}"
            if watch_triggers
            else "Take no position yet and wait for stronger evidence."
        )
        tactical = (
            f"Use staged entry once this trigger is met: {entry_triggers[0]}"
            if entry_triggers
            else "Use staged entry only after tradability and filing evidence are verified."
        )
        risk_control = (
            kill_criteria[0]
            if kill_criteria
            else "Exit or avoid if downside scenario probability becomes dominant."
        )

        return RetailSummary(
            verdict_line=verdict,
            what_i_see_now=what_i_see_now[:3],
            why_that_matters=why_that_matters[:3],
            the_good=the_good[:3],
            the_risk=the_risk[:3],
            simple_conclusion=simple_conclusion,
            key_data_points=key_data_points[:8],
            action_ideas=RetailActionIdeas(
                conservative=conservative,
                tactical=tactical,
                risk_control=risk_control,
            ),
            is_preliminary=preliminary,
        )

    def _build_investment_action(
        self,
        company_name: str,
        pre_ipo_funds: PreIpoBeneficiaryFunds,
        realistic_reco: ScenarioRecommendation,
        preliminary: bool,
        decision: Literal["buy", "watch", "avoid"],
        decision_scope: Literal["pre_ipo_fund", "post_ipo_direct", "no_trade"],
    ) -> str:
        usable = [
            c.fund_name
            for c in pre_ipo_funds.candidates
            if self._has_public_fund_style(c.fund_name)
            and c.confidence in ("high", "medium")
            and "not resolved" not in c.fund_name.lower()
        ]
        if decision == "avoid":
            return (
                f"Avoid {company_name} for now. Wait for materially better evidence quality or risk conditions before re-entry."
            )
        if preliminary or decision == "watch":
            return (
                f"Watch {company_name}. Wait for verified filing financials and tradability signals before taking a position."
            )
        if decision_scope == "pre_ipo_fund" and usable:
            top = ", ".join(usable[:3])
            return f"Buy pre-IPO fund exposure through {top}. Keep sizing staged as evidence updates arrive."
        return (
            f"Buy post-IPO direct exposure with a staged approach. Current posture: {realistic_reco.recommended_positioning}."
        )

    def _build_funds_to_consider(self, pre_ipo_funds: PreIpoBeneficiaryFunds) -> list[str]:
        out: list[str] = []
        for c in pre_ipo_funds.candidates:
            if "not resolved" in c.fund_name.lower():
                continue
            if "insufficient_evidence" in c.relation_type.lower():
                continue
            if self._is_private_backer(c.fund_name):
                continue
            if self._has_public_fund_style(c.fund_name) or c.confidence in ("high", "medium"):
                out.append(c.fund_name)
        return out[:5]

    def _build_what_to_watch(
        self,
        parser_output: dict[str, Any],
        scenarios_dict: dict[str, Any],
        harvester_output: dict[str, Any],
    ) -> list[str]:
        items: list[str] = []
        lockup = self._to_float(parser_output.get("lockup_period_days"))
        if lockup is not None and lockup > 0:
            items.append(f"Lock-up expiry: {int(lockup)} days after listing")

        risks = []
        for name in ("pessimistic", "realistic"):
            s = scenarios_dict.get(name)
            if isinstance(s, dict):
                kr = s.get("key_risks")
                if isinstance(kr, list) and kr:
                    risks.append(str(kr[0])[:80])
        if risks:
            items.append(f"Key risk: {risks[0]}")

        flagged = parser_output.get("flagged_sections")
        if isinstance(flagged, list) and flagged:
            sections = [str(f.get("section", "")) for f in flagged[:3] if isinstance(f, dict) and f.get("section")]
            if sections:
                items.append(f"Verify: {', '.join(sections)}")

        demand = parser_output.get("demand_signals")
        if isinstance(demand, dict):
            roadshow = str(demand.get("roadshow_sentiment") or "").lower()
            if "oversubscribed" in roadshow or "strong" in roadshow:
                items.append("Demand: oversubscribed; monitor for allocation updates")
            elif "weak" in roadshow:
                items.append("Demand: weak; watch pricing and allocation size")

        fred = harvester_output.get("fred_data")
        if isinstance(fred, dict):
            macro = str(fred.get("market_conditions") or "").lower()
            if "restrictive" in macro or "tightening" in macro:
                items.append("Macro: restrictive rates; watch Fed policy")

        if not items:
            items.append("SEC amendments and filing updates")
            items.append("Post-listing price action and volume")
        return items[:6]

    def _build_pre_ipo_beneficiary_funds(
        self,
        company_name: str,
        parser_output: dict[str, Any],
        harvester_output: dict[str, Any],
    ) -> PreIpoBeneficiaryFunds:
        candidate_scores: dict[str, dict[str, Any]] = {}

        funding_history = parser_output.get("funding_history")
        if isinstance(funding_history, list):
            for row in funding_history:
                if not isinstance(row, dict):
                    continue
                investors = row.get("investors")
                if not isinstance(investors, list):
                    continue
                for raw_name in investors:
                    self._bump_candidate(
                        candidate_scores,
                        fund_name=str(raw_name),
                        relation_type="direct_investor",
                        evidence=f"parser funding history investor mention: {str(raw_name).strip()}",
                        weight=2,
                    )

        crunchbase_data = harvester_output.get("crunchbase_data")
        if isinstance(crunchbase_data, dict):
            investors = crunchbase_data.get("investors")
            if isinstance(investors, list):
                for raw_name in investors:
                    self._bump_candidate(
                        candidate_scores,
                        fund_name=str(raw_name),
                        relation_type="direct_investor",
                        evidence=f"crunchbase investor mention: {str(raw_name).strip()}",
                        weight=2,
                    )

        text_blocks = self._text_blocks(harvester_output)
        for normalized_name, data in list(candidate_scores.items()):
            fund_name = str(data.get("fund_name") or "")
            mention_hits = 0
            for block in text_blocks:
                if self._name_in_text(fund_name, block):
                    mention_hits += 1
            if mention_hits > 0:
                data["score"] = int(data.get("score", 0)) + mention_hits
                relation = "direct_investor_with_corroboration"
                relations = data.get("relations")
                if isinstance(relations, set):
                    relations.add(relation)
                evidence = data.get("evidence")
                if isinstance(evidence, list):
                    evidence.append(f"name appears {mention_hits} time(s) across SEC/news text")
            if self._has_public_fund_style(fund_name):
                data["score"] = int(data.get("score", 0)) + 1
                relations = data.get("relations")
                if isinstance(relations, set):
                    relations.add("public_fund_style_naming")

        ranked = sorted(
            candidate_scores.values(),
            key=lambda item: (int(item.get("score", 0)), str(item.get("fund_name", "")).lower()),
            reverse=True,
        )
        candidates: list[BeneficiaryFundCandidate] = []
        for row in ranked[:5]:
            score = int(row.get("score", 0))
            confidence = "low"
            if score >= 6:
                confidence = "high"
            elif score >= 3:
                confidence = "medium"
            relations = row.get("relations")
            if isinstance(relations, set) and relations:
                relation_type = "|".join(sorted(relations))
            else:
                relation_type = "inferred_beneficiary"
            evidence = row.get("evidence")
            evidence_list = evidence[:4] if isinstance(evidence, list) else []
            candidates.append(
                BeneficiaryFundCandidate(
                    fund_name=str(row.get("fund_name") or "unknown"),
                    confidence=confidence,
                    relation_type=relation_type,
                    evidence=[str(item) for item in evidence_list if str(item).strip()],
                )
            )

        return PreIpoBeneficiaryFunds(
            candidates=candidates,
            methodology="Ranked by direct investor mentions plus corroboration in SEC/news text, with confidence bands from evidence density.",
        )

    def _is_preliminary(self, parser_output: dict[str, Any]) -> bool:
        return self._must_degrade_to_watch(parser_output)

    def _must_degrade_to_watch(self, parser_output: dict[str, Any]) -> bool:
        confidence = str(parser_output.get("data_confidence") or "").lower()
        if confidence == "low":
            return True

        flagged_sections = parser_output.get("flagged_sections")
        if not isinstance(flagged_sections, list):
            return False

        if len(flagged_sections) >= 4:
            return True

        financials = parser_output.get("financials")
        if isinstance(financials, dict):
            revenue = financials.get("revenue")
            if revenue is not None and "revenue_evidence" in financials and financials.get("revenue_evidence") is None:
                return True

            burn_rate_monthly = financials.get("burn_rate_monthly")
            if (
                burn_rate_monthly is not None
                and "burn_rate_monthly_evidence" in financials
                and financials.get("burn_rate_monthly_evidence") is None
            ):
                return True

            cash_runway_months = financials.get("cash_runway_months")
            if (
                cash_runway_months is not None
                and "cash_runway_months_evidence" in financials
                and financials.get("cash_runway_months_evidence") is None
            ):
                return True

        if (
            "use_of_proceeds_evidence" in parser_output
            and parser_output.get("use_of_proceeds_evidence") is None
            and "use_of_proceeds" in parser_output
            and parser_output.get("use_of_proceeds") is not None
        ):
            return True

        if (
            "risk_factors_evidence" in parser_output
            and isinstance(parser_output.get("risk_factors_evidence"), list)
            and parser_output.get("risk_factors_evidence") == []
            and "risk_factors" in parser_output
            and isinstance(parser_output.get("risk_factors"), list)
            and parser_output.get("risk_factors") != []
        ):
            return True

        return False

    def _preliminary_rationale(
        self,
        positioning: str,
        parser_output: dict[str, Any],
        top_driver: str,
    ) -> str:
        flagged_sections = parser_output.get("flagged_sections")
        flagged_count = len(flagged_sections) if isinstance(flagged_sections, list) else 0
        return (
            f"Low-confidence preliminary posture: use {positioning.lower()} while filing evidence remains incomplete. "
            f"Current support is limited to {top_driver[:120]}, and {flagged_count} sections still require manual verification."
        )

    def _preliminary_client_paragraph(
        self,
        company_name: str,
        scenario_name: str,
        positioning: str,
        conviction: str,
        rationale: str,
        risk_warning: str,
        parser_output: dict[str, Any],
    ) -> str:
        confidence = str(parser_output.get("data_confidence") or "unknown")
        flagged_sections = parser_output.get("flagged_sections")
        flagged_count = len(flagged_sections) if isinstance(flagged_sections, list) else 0
        return (
            f"For the {scenario_name} case on {company_name}, this is a preliminary recommendation rather than a client-ready conclusion. "
            f"Our current posture is {positioning}, but conviction should be treated as {conviction} only in a monitoring sense because the underlying extraction quality is {confidence}. "
            f"{rationale} At this stage, the output should be used to frame follow-up diligence, not to anchor sizing decisions or communicate a strong valuation view. "
            f"Key missing items still sit in the filing record, including core financial disclosures, offering mechanics, or use-of-proceeds detail where applicable, and {flagged_count} sections remain flagged for verification. "
            f"{risk_warning} The right next move is to wait for cleaner SEC detail, better investor corroboration, and firmer demand evidence before converting this monitored stance into a stronger recommendation."
        )

    def _bump_candidate(
        self,
        store: dict[str, dict[str, Any]],
        fund_name: str,
        relation_type: str,
        evidence: str,
        weight: int,
    ) -> None:
        cleaned = fund_name.strip()
        normalized = self._normalize_name(cleaned)
        if not cleaned or not normalized:
            return
        current = store.get(normalized)
        if current is None:
            current = {"fund_name": cleaned, "score": 0, "relations": set(), "evidence": []}
            store[normalized] = current
        current["score"] = int(current.get("score", 0)) + weight
        relations = current.get("relations")
        if isinstance(relations, set):
            relations.add(relation_type)
        evidence_list = current.get("evidence")
        if isinstance(evidence_list, list):
            evidence_list.append(evidence)

    def _text_blocks(self, harvester_output: dict[str, Any]) -> list[str]:
        blocks: list[str] = []
        sec_filings = harvester_output.get("sec_filings")
        if isinstance(sec_filings, list):
            for filing in sec_filings:
                if not isinstance(filing, dict):
                    continue
                text = str(filing.get("text") or "").strip()
                if text:
                    blocks.append(text.lower())

        news_articles = harvester_output.get("news_articles")
        if isinstance(news_articles, list):
            for article in news_articles:
                if not isinstance(article, dict):
                    continue
                title = str(article.get("title") or "").strip()
                content = str(article.get("content") or "").strip()
                if title or content:
                    blocks.append(f"{title} {content}".lower())
        return blocks

    def _normalize_name(self, name: str) -> str:
        normalized = name.lower()
        normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _name_in_text(self, name: str, text: str) -> bool:
        normalized_name = self._normalize_name(name)
        if not normalized_name or not text:
            return False
        return normalized_name in text

    def _has_public_fund_style(self, fund_name: str) -> bool:
        lowered = fund_name.lower()
        tokens = ("fund", "capital", "ventures", "asset", "management", "partners", "growth")
        return any(token in lowered for token in tokens)

    def _is_private_backer(self, fund_name: str) -> bool:
        lowered = (fund_name or "").lower()

        private_markers = (
            "venture capital",
            "vc",
            "ventures",
            "venture",
            "angel",
            "seed",
            "early stage",
            "incubator",
            "private equity",
            "private fund",
            "series a",
            "series b",
            "series c",
        )

        public_markers = (
            "fund",
            "asset",
            "management",
            "investment",
            "trust",
            "etf",
            "ucits",
            "reit",
            "portfolio",
        )

        if any(marker in lowered for marker in private_markers):
            return True
        if any(marker in lowered for marker in public_markers):
            return False

        # Conservative default: if we can't classify it as a public-style vehicle,
        # treat it as a likely private backer.
        return True

    def _has_minimum_tradability_evidence(self, parser_output: dict[str, Any]) -> bool:
        if not isinstance(parser_output, dict):
            return False

        float_details = parser_output.get("float_details")
        if not isinstance(float_details, dict):
            return False

        public_float = self._to_float(float_details.get("public_float"))
        if public_float is None or public_float <= 0:
            return False

        lockup = self._to_float(parser_output.get("lockup_period_days"))
        if lockup is None or lockup <= 0:
            return False

        return True

    def _scenario_probability(self, scenarios_dict: dict[str, Any], name: str) -> float:
        scenario = scenarios_dict.get(name)
        if not isinstance(scenario, dict):
            return 0.0
        return self._to_float(scenario.get("probability")) or 0.0

    def _fmt(self, value: float | None) -> str:
        if value is None:
            return "n/a"
        return f"{round(value, 2)}"

    def _fmt_money(self, value: float | None) -> str:
        if value is None:
            return "n/a"
        if value >= 1_000_000_000:
            return f"${round(value / 1_000_000_000, 2)}B"
        if value >= 1_000_000:
            return f"${round(value / 1_000_000, 2)}M"
        if value >= 1_000:
            return f"${round(value / 1_000, 2)}K"
        return f"${round(value, 2)}"

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
