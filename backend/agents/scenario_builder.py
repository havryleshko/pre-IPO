from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel

from backend.agents.prospectus_parser import ProspectusParser
from backend.database.queries import get_analysis_by_id, save_scenario_output
from backend.models.parser_output import ActualResult, S1Projection
from backend.models.scenario_output import (
    DeliveryEvidence,
    PatternFlag,
    PricePerformance,
    PriceTargets,
    ScenarioDetails,
    ScenarioOutput,
    ScenarioSet,
)
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

        price_performance = self._price_performance_from_harvester(harvester_output)
        baseline_price = price_performance.current_price if price_performance is not None else None

        s1_rows, actual_rows = self._hydrate_s1_and_actuals(parser_output)
        delivery_evidence: list[DeliveryEvidence] = []
        if s1_rows and actual_rows:
            delivery_evidence = ProspectusParser().compare_s1_to_10k(s1_rows, actual_rows)

        delivery_score, ipo_delivery_verdict = self.compute_delivery_score(delivery_evidence, price_performance)
        patterns_flagged = self.detect_ipo_patterns(
            parser_output, price_performance, delivery_evidence=delivery_evidence
        )

        pessimistic_targets = self._price_targets(
            "pessimistic", sector_performance, burn_rate, revenue, institutional_interest, baseline_price
        )
        realistic_targets = self._price_targets(
            "realistic", sector_performance, burn_rate, revenue, institutional_interest, baseline_price
        )
        optimistic_targets = self._price_targets(
            "optimistic", sector_performance, burn_rate, revenue, institutional_interest, baseline_price
        )

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
            ipo_delivery_verdict=ipo_delivery_verdict,
            delivery_score=delivery_score,
            delivery_evidence=delivery_evidence,
            price_performance=price_performance,
            patterns_flagged=patterns_flagged,
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

    def compute_delivery_score(
        self,
        delivery_evidence: list[DeliveryEvidence],
        price_performance: PricePerformance | None,
    ) -> tuple[float, Literal["delivered", "underdelivered", "mixed"]]:
        ev_delta = 0.0
        for row in delivery_evidence:
            if row.verdict == "met":
                ev_delta += 9.0
            elif row.verdict == "exceeded":
                ev_delta += 11.0
            else:
                ev_delta -= 11.0
        ev_delta = max(-35.0, min(35.0, ev_delta))
        score = 50.0 + ev_delta

        if price_performance is not None:
            perf = price_performance.performance_since_ipo_pct
            if perf is not None:
                if perf > 15.0:
                    score += 12.0
                elif perf > 0.0:
                    score += 6.0
                elif perf < -15.0:
                    score -= 12.0
                elif perf < 0.0:
                    score -= 6.0

        score = max(0.0, min(100.0, round(score, 2)))
        if score >= 65.0:
            verdict: Literal["delivered", "underdelivered", "mixed"] = "delivered"
        elif score <= 40.0:
            verdict = "underdelivered"
        else:
            verdict = "mixed"
        return score, verdict

    def detect_ipo_patterns(
        self,
        parser_output: dict[str, Any],
        price_performance: PricePerformance | None,
        delivery_evidence: list[DeliveryEvidence] | None = None,
    ) -> list[PatternFlag]:
        evidence = delivery_evidence or []
        flags: list[PatternFlag] = []

        insider = self._to_float(parser_output.get("insider_selling_percentage"))
        if insider is not None and insider >= 30.0 and price_performance is not None:
            cliff = price_performance.price_at_lock_up_cliff
            current = price_performance.current_price
            if cliff is not None and current is not None and cliff > 0:
                if current <= cliff * 0.85:
                    flags.append(
                        PatternFlag(
                            signal="insider_selling_lockup_cliff_pressure",
                            was_visible_at_ipo=True,
                            outcome=(
                                f"Insider selling {insider:.0f}%+ at IPO; price at cliff {cliff:.2f} vs "
                                f"current {current:.2f} implies post-lock-up pressure."
                            ),
                        )
                    )

        for row in evidence:
            claim_lower = row.claim.strip().lower()
            if claim_lower.startswith("burn_rate") and row.verdict == "missed":
                flags.append(
                    PatternFlag(
                        signal="burn_rate_forecast_inaccuracy",
                        was_visible_at_ipo=True,
                        outcome="S-1 burn projection materially missed vs first 10-K actuals.",
                    )
                )
                break

        demand = parser_output.get("demand_signals") if isinstance(parser_output.get("demand_signals"), dict) else {}
        anchors = demand.get("anchor_investors") if isinstance(demand.get("anchor_investors"), list) else []
        if anchors:
            rev_ok = any(
                r.claim.strip().lower().startswith("revenue") and r.verdict in ("met", "exceeded")
                for r in evidence
            )
            if rev_ok:
                out = "Anchor syndicate present; revenue delivery met or exceeded S-1 framing."
            else:
                out = "Anchor syndicate visible at IPO; monitor revenue and margin delivery vs prospectus."
            flags.append(
                PatternFlag(
                    signal="anchor_investor_syndicate",
                    was_visible_at_ipo=True,
                    outcome=out,
                )
            )

        return flags

    def _price_performance_from_harvester(self, harvester_output: dict[str, Any]) -> PricePerformance | None:
        raw = harvester_output.get("ipo_price_history")
        if not isinstance(raw, dict):
            return None
        lock_raw = raw.get("lock_up_cliff_date")
        lock_parsed: date | None = None
        if isinstance(lock_raw, date):
            lock_parsed = lock_raw
        elif isinstance(lock_raw, datetime):
            lock_parsed = lock_raw.date()
        elif isinstance(lock_raw, str) and lock_raw.strip():
            try:
                lock_parsed = date.fromisoformat(lock_raw.strip()[:10])
            except ValueError:
                lock_parsed = None
        pp = PricePerformance(
            ipo_price=self._to_float(raw.get("ipo_price")),
            current_price=self._to_float(raw.get("current_price")),
            peak_price=self._to_float(raw.get("peak_price")),
            trough_price=self._to_float(raw.get("trough_price")),
            performance_since_ipo_pct=self._to_float(raw.get("performance_since_ipo_pct")),
            lock_up_cliff_date=lock_parsed,
            price_at_lock_up_cliff=self._to_float(raw.get("price_at_lock_up_cliff")),
        )
        if (
            pp.ipo_price is None
            and pp.current_price is None
            and pp.peak_price is None
            and pp.trough_price is None
            and pp.performance_since_ipo_pct is None
            and pp.price_at_lock_up_cliff is None
            and pp.lock_up_cliff_date is None
        ):
            return None
        return pp

    def _hydrate_s1_and_actuals(
        self, parser_output: dict[str, Any]
    ) -> tuple[list[S1Projection], list[ActualResult]]:
        s1_list: list[S1Projection] = []
        raw_s1 = parser_output.get("s1_projections")
        if isinstance(raw_s1, list):
            for item in raw_s1:
                if isinstance(item, dict):
                    try:
                        s1_list.append(S1Projection.model_validate(item))
                    except Exception:
                        continue
        act_list: list[ActualResult] = []
        raw_a = parser_output.get("actuals")
        if isinstance(raw_a, list):
            for item in raw_a:
                if isinstance(item, dict):
                    try:
                        act_list.append(ActualResult.model_validate(item))
                    except Exception:
                        continue
        return s1_list, act_list

    def _price_targets(
        self,
        scenario: str,
        sector_performance: float | None,
        burn_rate: float | None,
        revenue: float | None,
        institutional_interest: str,
        baseline_price: float | None,
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
            y1_index = 80.0 + sector * 0.40 - burn_penalty * 1.2 + demand_bonus * 0.3
        elif scenario == "optimistic":
            y1_index = 132.0 + sector * 0.60 - burn_penalty * 0.6 + demand_bonus * 1.3
        else:
            y1_index = 106.0 + sector * 0.45 - burn_penalty + demand_bonus * 0.8

        baseline = baseline_price if baseline_price is not None and baseline_price > 0 else 100.0
        y1 = baseline * (y1_index / 100.0)
        d30 = baseline + (y1 - baseline) * (30.0 / 365.0)
        d90 = baseline + (y1 - baseline) * (90.0 / 365.0)

        return PriceTargets(
            **{
                "30_days": round(max(0.01, d30), 2),
                "90_days": round(max(0.01, d90), 2),
                "1_year": round(max(0.01, y1), 2),
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
        if roadshow and not roadshow.lower().startswith("no clear roadshow"):
            drivers.append(f"Roadshow: {roadshow[:200]}")

        fred = harvester_output.get("fred_data") if isinstance(harvester_output.get("fred_data"), dict) else {}
        macro = str(fred.get("market_conditions") or "").strip()
        if macro:
            drivers.append(f"Macro: {macro}")

        sec_filings = harvester_output.get("sec_filings") if isinstance(harvester_output.get("sec_filings"), list) else []
        if sec_filings:
            drivers.append(f"SEC filings captured: {len(sec_filings)}")

        news_articles = harvester_output.get("news_articles") if isinstance(harvester_output.get("news_articles"), list) else []
        if news_articles:
            for article in news_articles[:2]:
                if not isinstance(article, dict):
                    continue
                title = str(article.get("title") or "").strip()
                source = str(article.get("source") or "news")
                if title:
                    drivers.append(f"News ({source}): {title[:180]}")

        funding_history = parser_output.get("funding_history") if isinstance(parser_output.get("funding_history"), list) else []
        if funding_history:
            latest_round = funding_history[0] if isinstance(funding_history[0], dict) else {}
            round_name = str(latest_round.get("round") or "recent round")
            amount = self._to_float(latest_round.get("amount"))
            if amount is not None:
                drivers.append(f"Crunchbase funding: {round_name} {self._fmt_money(amount)}")

        if not drivers:
            drivers.append("Limited evidence available from SEC, news, and market inputs.")
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
        macro = "unknown"
        fred = harvester_output.get("fred_data")
        if isinstance(fred, dict):
            macro = str(fred.get("market_conditions") or "unknown")
        sec_count = len(harvester_output.get("sec_filings") or []) if isinstance(harvester_output.get("sec_filings"), list) else 0
        news_count = len(harvester_output.get("news_articles") or []) if isinstance(harvester_output.get("news_articles"), list) else 0
        funding_rounds = len(parser_output.get("funding_history") or []) if isinstance(parser_output.get("funding_history"), list) else 0
        demand_signals = parser_output.get("demand_signals") if isinstance(parser_output.get("demand_signals"), dict) else {}
        institutional_interest = str(demand_signals.get("institutional_interest") or "unknown")
        sector = ""
        yahoo = harvester_output.get("yahoo_finance_data") if isinstance(harvester_output.get("yahoo_finance_data"), dict) else {}
        sector_perf = self._to_float(yahoo.get("sector_90d_performance"))
        if sector_perf is not None:
            sector = f", Yahoo sector 90d {round(sector_perf, 2)}"
        return (
            f"{scenario} probability {weights[scenario]}% from rules [{rule_block}]. "
            f"Sources: SEC filings {sec_count}, news articles {news_count}, Crunchbase funding rounds {funding_rounds}, "
            f"FRED macro {macro}{sector}. Parser confidence {confidence}; institutional interest {institutional_interest}; "
            f"qualitative adjustment {llm_reason}."
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

    def _fmt_money(self, value: float) -> str:
        if value >= 1_000_000_000:
            return f"${round(value / 1_000_000_000, 2)}B"
        if value >= 1_000_000:
            return f"${round(value / 1_000_000, 2)}M"
        if value >= 1_000:
            return f"${round(value / 1_000, 2)}K"
        return f"${round(value, 2)}"
