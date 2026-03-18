import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from backend.database.queries import get_analysis_by_id, save_recommendation_output
from backend.models.recommendation_output import (
    BeneficiaryFundCandidate,
    PreIpoBeneficiaryFunds,
    RecommendationOutput,
    Recommendations,
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

        summary = self._plain_english_summary(
            company_name=company_name,
            pre_ipo_funds=pre_ipo_funds,
            pessimistic=pessimistic_reco,
            realistic=realistic_reco,
            optimistic=optimistic_reco,
            scenarios_dict=scenarios_dict,
            parser_output=parser_output,
            harvester_output=harvester_output,
        )

        investment_action = self._build_investment_action(
            company_name=company_name,
            pre_ipo_funds=pre_ipo_funds,
            realistic_reco=realistic_reco,
            preliminary=preliminary,
        )
        funds_to_consider = self._build_funds_to_consider(pre_ipo_funds)
        what_to_watch = self._build_what_to_watch(
            parser_output=parser_output,
            scenarios_dict=scenarios_dict,
            harvester_output=harvester_output,
        )

        return RecommendationOutput(
            company_name=company_name,
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
            generated_at=datetime.now(timezone.utc),
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
        drivers = scenario_data.get("drivers") if isinstance(scenario_data.get("drivers"), list) else []
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
        targets = scenario_data.get("price_targets") if isinstance(scenario_data.get("price_targets"), dict) else {}
        p30 = self._to_float(targets.get("30_days"))
        p90 = self._to_float(targets.get("90_days"))
        p1y = self._to_float(targets.get("1_year"))
        financials = parser_output.get("financials") if isinstance(parser_output.get("financials"), dict) else {}
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
                f"Preliminary recommendation for {company_name}: {realistic.recommended_positioning}. "
                f"Current evidence is low confidence, with {flagged_count} material filing gaps and {source_count} active source checks completed. "
                f"{funds_note} Treat this as a monitored posture until financial, float, and demand evidence are verified."
            )
        p = self._scenario_probability(scenarios_dict, "pessimistic")
        r = self._scenario_probability(scenarios_dict, "realistic")
        o = self._scenario_probability(scenarios_dict, "optimistic")
        top_funds = ", ".join(item.fund_name for item in pre_ipo_funds.candidates[:3])
        pre_ipo_block = top_funds if top_funds else "no high-confidence pre-IPO beneficiary funds were identified"
        return (
            f"For {company_name}, pre-IPO beneficiary analysis points to {pre_ipo_block}. For post-IPO positioning, we map downside "
            f"({round(p, 2)}%), base ({round(r, 2)}%), and upside ({round(o, 2)}%) paths to "
            f"{pessimistic.recommended_positioning}; {realistic.recommended_positioning}; and {optimistic.recommended_positioning}, "
            f"so clients can align exposure to changing conviction while separating private-exposure thesis from listing-outcome thesis."
        )

    def _build_investment_action(
        self,
        company_name: str,
        pre_ipo_funds: PreIpoBeneficiaryFunds,
        realistic_reco: ScenarioRecommendation,
        preliminary: bool,
    ) -> str:
        usable = [
            c.fund_name
            for c in pre_ipo_funds.candidates
            if self._has_public_fund_style(c.fund_name)
            and c.confidence in ("high", "medium")
            and "not resolved" not in c.fund_name.lower()
        ]
        if preliminary:
            if usable:
                return (
                    f"Consider {usable[0]} for pre-IPO exposure; watch for SEC filing updates and verified financials before sizing."
                )
            return (
                f"Hold: wait for verified S-1 financials and float details before considering any fund. "
                f"Monitor {company_name} for lock-up expiry and demand signals."
            )
        if usable:
            top = ", ".join(usable[:3])
            return (
                f"Buy: {top} for pre-IPO exposure. Position: {realistic_reco.recommended_positioning}. "
                f"Watch lock-up expiry and key risk factors before adding."
            )
        return (
            f"Post-IPO: {realistic_reco.recommended_positioning}. "
            f"No high-confidence public fund found. Watch for funds with {company_name} in holdings; "
            f"verify lock-up expiry and demand signals before sizing."
        )

    def _build_funds_to_consider(self, pre_ipo_funds: PreIpoBeneficiaryFunds) -> list[str]:
        out: list[str] = []
        for c in pre_ipo_funds.candidates:
            if "not resolved" in c.fund_name.lower():
                continue
            if "insufficient_evidence" in c.relation_type.lower():
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
