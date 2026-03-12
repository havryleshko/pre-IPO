from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from backend.database.queries import get_analysis_by_id, save_scenario_output
from backend.models.scenario_output import PriceTargets, ScenarioDetails, ScenarioOutput, ScenarioSet
from backend.services.agent_run_logger import (
    log_agent_run_completed,
    log_agent_run_failed,
    log_agent_run_start,
)


class ScenarioBuilderInput(BaseModel):
    analysis_id: str


class ScenarioBuilderResult(BaseModel):
    analysis_id: str


class ScenarioBuilder:
    async def run(self, payload: ScenarioBuilderInput) -> ScenarioBuilderResult:
        run_record = await log_agent_run_start(
            analysis_id=payload.analysis_id,
            agent_name="scenario_builder",
            input_reference=f"analysis_id={payload.analysis_id}",
        )
        run_id: str = str(run_record["id"]) if run_record else ""

        try:
            analysis = await get_analysis_by_id(payload.analysis_id)
            if analysis is None:
                raise RuntimeError(f"Analysis not found for analysis_id={payload.analysis_id}")

            parser_output = analysis.get("parser_output")
            harvester_output = analysis.get("harvester_output")
            if not isinstance(parser_output, dict):
                parser_output = {}
            if not isinstance(harvester_output, dict):
                harvester_output = {}

            scenario_output = self._build_output(
                company_name=str(analysis.get("company_name") or "unknown"),
                complexity_tier=str(analysis.get("complexity_tier") or "standard"),
                parser_output=parser_output,
                harvester_output=harvester_output,
            )
            await save_scenario_output(
                analysis_id=payload.analysis_id,
                output=scenario_output.model_dump(mode="json", by_alias=True),
            )
        except Exception as exc:
            await log_agent_run_failed(run_id=run_id, error_message=str(exc))
            raise

        await log_agent_run_completed(
            run_id=run_id,
            output_reference=f"analysis_id={payload.analysis_id}",
        )
        return ScenarioBuilderResult(analysis_id=payload.analysis_id)

    def _build_output(
        self,
        company_name: str,
        complexity_tier: str,
        parser_output: dict[str, Any],
        harvester_output: dict[str, Any],
    ) -> ScenarioOutput:
        weights = {"pessimistic": 30.0, "realistic": 40.0, "optimistic": 30.0}
        rules_applied: dict[str, list[str]] = {"pessimistic": [], "realistic": [], "optimistic": []}

        financials = parser_output.get("financials") if isinstance(parser_output.get("financials"), dict) else {}
        float_details = parser_output.get("float_details") if isinstance(parser_output.get("float_details"), dict) else {}
        demand_signals = parser_output.get("demand_signals") if isinstance(parser_output.get("demand_signals"), dict) else {}
        risk_factors = parser_output.get("risk_factors") if isinstance(parser_output.get("risk_factors"), list) else []

        revenue = self._to_float(financials.get("revenue"))
        burn_rate = self._to_float(financials.get("burn_rate_monthly"))
        insider_selling = self._to_float(parser_output.get("insider_selling_percentage"))
        lockup_days = self._to_float(parser_output.get("lockup_period_days"))
        offering_type = str(parser_output.get("offering_type") or "primary").lower()

        anchors = demand_signals.get("anchor_investors") if isinstance(demand_signals.get("anchor_investors"), list) else []
        institutional_interest = str(demand_signals.get("institutional_interest") or "unknown").lower()

        yahoo = harvester_output.get("yahoo_finance_data") if isinstance(harvester_output.get("yahoo_finance_data"), dict) else {}
        sector_performance = self._to_float(yahoo.get("sector_90d_performance"))

        public_float = self._to_float(float_details.get("public_float"))
        total_shares = self._to_float(float_details.get("total_shares_offered"))
        public_float_pct = self._public_float_percentage(public_float, total_shares)

        if burn_rate is not None and burn_rate > 0 and (revenue is None or revenue <= 0):
            self._apply_rule(weights, rules_applied, "pessimistic", 10.0, "high_burn_no_revenue")

        if insider_selling is not None and insider_selling >= 30.0:
            self._apply_rule(weights, rules_applied, "pessimistic", 10.0, "insider_selling_ge_30")

        if lockup_days is not None and lockup_days < 90.0:
            self._apply_rule(weights, rules_applied, "pessimistic", 5.0, "lockup_under_90_days")

        if anchors:
            self._apply_rule(weights, rules_applied, "optimistic", 10.0, "anchor_investors_present")

        if sector_performance is not None and sector_performance > 0:
            self._apply_rule(weights, rules_applied, "optimistic", 10.0, "hot_sector_positive_90d")

        if public_float_pct is not None and public_float_pct < 20.0:
            self._apply_rule(weights, rules_applied, "optimistic", 5.0, "low_public_float_under_20_pct")

        if offering_type == "primary":
            self._apply_rule(weights, rules_applied, "optimistic", 5.0, "primary_offering_only")

        if institutional_interest == "high":
            self._apply_rule(weights, rules_applied, "optimistic", 10.0, "high_institutional_interest")

        weights = self._normalize_weights(weights)

        llm_adjustment, llm_reason = self._llm_style_adjustment(parser_output, harvester_output)
        if llm_adjustment != 0.0:
            weights["optimistic"] += llm_adjustment
            weights["pessimistic"] -= llm_adjustment
        weights = self._normalize_weights(weights)

        pessimistic_targets = self._price_targets("pessimistic", sector_performance, burn_rate, revenue, institutional_interest)
        realistic_targets = self._price_targets("realistic", sector_performance, burn_rate, revenue, institutional_interest)
        optimistic_targets = self._price_targets("optimistic", sector_performance, burn_rate, revenue, institutional_interest)

        pessimistic_drivers = self._drivers_for_scenario("pessimistic", rules_applied, parser_output, harvester_output)
        realistic_drivers = self._drivers_for_scenario("realistic", rules_applied, parser_output, harvester_output)
        optimistic_drivers = self._drivers_for_scenario("optimistic", rules_applied, parser_output, harvester_output)

        pessimistic = ScenarioDetails(
            probability=weights["pessimistic"],
            drivers=pessimistic_drivers,
            key_risks=[str(item) for item in risk_factors[:5]],
            price_targets=pessimistic_targets,
            weighting_rationale=self._rationale("pessimistic", weights, rules_applied, parser_output, harvester_output, llm_reason),
            rules_applied=rules_applied["pessimistic"],
        )
        realistic = ScenarioDetails(
            probability=weights["realistic"],
            drivers=realistic_drivers,
            key_risks=[str(item) for item in risk_factors[:3]],
            price_targets=realistic_targets,
            weighting_rationale=self._rationale("realistic", weights, rules_applied, parser_output, harvester_output, llm_reason),
            rules_applied=rules_applied["realistic"],
        )
        optimistic = ScenarioDetails(
            probability=weights["optimistic"],
            drivers=optimistic_drivers,
            key_risks=[str(item) for item in risk_factors[:2]],
            price_targets=optimistic_targets,
            weighting_rationale=self._rationale("optimistic", weights, rules_applied, parser_output, harvester_output, llm_reason),
            rules_applied=rules_applied["optimistic"],
        )

        probability_sum = round(pessimistic.probability + realistic.probability + optimistic.probability, 2)
        return ScenarioOutput(
            company_name=company_name,
            complexity_tier=self._complexity_tier(complexity_tier),
            scenarios=ScenarioSet(
                pessimistic=pessimistic,
                realistic=realistic,
                optimistic=optimistic,
            ),
            probability_sum_check=probability_sum,
            llm_adjustment_applied=llm_adjustment != 0.0,
            llm_adjustment_rationale=llm_reason if llm_adjustment != 0.0 else None,
            built_at=datetime.now(timezone.utc),
        )

    def _apply_rule(
        self,
        weights: dict[str, float],
        rules_applied: dict[str, list[str]],
        target: str,
        shift: float,
        rule_name: str,
    ) -> None:
        if target == "pessimistic":
            weights["pessimistic"] += shift
            weights["realistic"] -= shift / 2
            weights["optimistic"] -= shift / 2
            rules_applied["pessimistic"].append(rule_name)
        elif target == "optimistic":
            weights["optimistic"] += shift
            weights["realistic"] -= shift / 2
            weights["pessimistic"] -= shift / 2
            rules_applied["optimistic"].append(rule_name)

    def _normalize_weights(self, weights: dict[str, float]) -> dict[str, float]:
        bounded = {
            "pessimistic": max(1.0, weights["pessimistic"]),
            "realistic": max(1.0, weights["realistic"]),
            "optimistic": max(1.0, weights["optimistic"]),
        }
        total = bounded["pessimistic"] + bounded["realistic"] + bounded["optimistic"]
        normalized = {
            "pessimistic": round((bounded["pessimistic"] / total) * 100.0, 2),
            "realistic": round((bounded["realistic"] / total) * 100.0, 2),
            "optimistic": round((bounded["optimistic"] / total) * 100.0, 2),
        }
        delta = round(100.0 - sum(normalized.values()), 2)
        if delta != 0:
            largest = max(normalized, key=normalized.get)
            normalized[largest] = round(normalized[largest] + delta, 2)
        return normalized

    def _llm_style_adjustment(self, parser_output: dict[str, Any], harvester_output: dict[str, Any]) -> tuple[float, str]:
        score = 0.0
        reasons: list[str] = []

        confidence = str(parser_output.get("data_confidence") or "medium").lower()
        if confidence == "high":
            score += 4.0
            reasons.append("high parser confidence")
        elif confidence == "low":
            score -= 4.0
            reasons.append("low parser confidence")

        risk_factors = parser_output.get("risk_factors") if isinstance(parser_output.get("risk_factors"), list) else []
        if len(risk_factors) >= 8:
            score -= 3.0
            reasons.append("elevated risk factor count")

        roadshow_sentiment = ""
        demand_signals = parser_output.get("demand_signals")
        if isinstance(demand_signals, dict):
            roadshow_sentiment = str(demand_signals.get("roadshow_sentiment") or "").lower()
        if any(token in roadshow_sentiment for token in ("strong", "oversubscribed", "high demand")):
            score += 4.0
            reasons.append("positive roadshow signal")
        if any(token in roadshow_sentiment for token in ("weak", "soft demand", "cautious")):
            score -= 4.0
            reasons.append("weak roadshow signal")

        fred = harvester_output.get("fred_data") if isinstance(harvester_output.get("fred_data"), dict) else {}
        macro = str(fred.get("market_conditions") or "").lower()
        if "restrictive" in macro or "tightening" in macro:
            score -= 3.0
            reasons.append("restrictive macro regime")
        if "easing" in macro or "accommodative" in macro:
            score += 3.0
            reasons.append("supportive macro regime")

        twitter = harvester_output.get("twitter_data") if isinstance(harvester_output.get("twitter_data"), dict) else {}
        sentiment = twitter.get("sentiment_score") if isinstance(twitter.get("sentiment_score"), dict) else {}
        positive = self._to_float(sentiment.get("positive")) or 0.0
        negative = self._to_float(sentiment.get("negative")) or 0.0
        if positive - negative > 0.2:
            score += 2.0
            reasons.append("positive verified social sentiment")
        elif negative - positive > 0.2:
            score -= 2.0
            reasons.append("negative verified social sentiment")

        adjustment = max(-15.0, min(15.0, round(score, 2)))
        rationale = ", ".join(reasons) if reasons else "no material qualitative adjustment factors"
        return adjustment, rationale

    def _price_targets(
        self,
        scenario: str,
        sector_performance: float | None,
        burn_rate: float | None,
        revenue: float | None,
        institutional_interest: str,
    ) -> PriceTargets:
        sector = sector_performance or 0.0
        burn_penalty = 0.0
        if burn_rate is not None and burn_rate > 0 and (revenue is None or revenue <= 0):
            burn_penalty = 6.0
        demand_bonus = 0.0
        if institutional_interest == "high":
            demand_bonus = 5.0
        elif institutional_interest == "low":
            demand_bonus = -5.0

        if scenario == "pessimistic":
            d30 = 92.0 + sector * 0.25 - burn_penalty + demand_bonus * 0.2
            d90 = 86.0 + sector * 0.30 - burn_penalty * 1.1 + demand_bonus * 0.2
            y1 = 80.0 + sector * 0.40 - burn_penalty * 1.2 + demand_bonus * 0.3
        elif scenario == "optimistic":
            d30 = 108.0 + sector * 0.35 - burn_penalty * 0.4 + demand_bonus
            d90 = 118.0 + sector * 0.45 - burn_penalty * 0.5 + demand_bonus * 1.1
            y1 = 132.0 + sector * 0.60 - burn_penalty * 0.6 + demand_bonus * 1.3
        else:
            d30 = 100.0 + sector * 0.30 - burn_penalty * 0.8 + demand_bonus * 0.5
            d90 = 102.0 + sector * 0.35 - burn_penalty * 0.9 + demand_bonus * 0.6
            y1 = 106.0 + sector * 0.45 - burn_penalty + demand_bonus * 0.8

        return PriceTargets(
            **{
                "30_days": round(max(1.0, d30), 2),
                "90_days": round(max(1.0, d90), 2),
                "1_year": round(max(1.0, y1), 2),
            }
        )

    def _drivers_for_scenario(
        self,
        scenario: str,
        rules_applied: dict[str, list[str]],
        parser_output: dict[str, Any],
        harvester_output: dict[str, Any],
    ) -> list[str]:
        drivers: list[str] = []
        if scenario == "optimistic" and rules_applied["optimistic"]:
            drivers.extend([f"Rule trigger: {name}" for name in rules_applied["optimistic"][:4]])
        if scenario == "pessimistic" and rules_applied["pessimistic"]:
            drivers.extend([f"Rule trigger: {name}" for name in rules_applied["pessimistic"][:4]])

        demand = parser_output.get("demand_signals") if isinstance(parser_output.get("demand_signals"), dict) else {}
        roadshow = str(demand.get("roadshow_sentiment") or "").strip()
        if roadshow:
            drivers.append(f"Roadshow: {roadshow[:200]}")

        fred = harvester_output.get("fred_data") if isinstance(harvester_output.get("fred_data"), dict) else {}
        macro = str(fred.get("market_conditions") or "").strip()
        if macro:
            drivers.append(f"Macro: {macro}")

        if not drivers:
            drivers.append("No strong directional driver detected in current inputs.")
        return drivers[:6]

    def _rationale(
        self,
        scenario: str,
        weights: dict[str, float],
        rules_applied: dict[str, list[str]],
        parser_output: dict[str, Any],
        harvester_output: dict[str, Any],
        llm_reason: str,
    ) -> str:
        rule_names = rules_applied.get(scenario) or []
        rule_block = ", ".join(rule_names) if rule_names else "no direct rules"
        confidence = str(parser_output.get("data_confidence") or "unknown")
        macro = ""
        fred = harvester_output.get("fred_data")
        if isinstance(fred, dict):
            macro = str(fred.get("market_conditions") or "unknown")
        return (
            f"{scenario} probability set at {weights[scenario]}% from rules [{rule_block}], "
            f"parser confidence {confidence}, macro regime {macro}, qualitative adjustment: {llm_reason}."
        )

    def _public_float_percentage(self, public_float: float | None, total_shares: float | None) -> float | None:
        if public_float is None or total_shares is None or total_shares <= 0:
            return None
        return (public_float / total_shares) * 100.0

    def _complexity_tier(self, value: str) -> str:
        text = value.lower().strip()
        if text in ("simple", "standard", "complex"):
            return text
        return "standard"

    def _to_float(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip().replace(",", "")
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None
