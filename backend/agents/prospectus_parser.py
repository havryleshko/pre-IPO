import re
from datetime import date, datetime, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel

from backend.database.queries import get_analysis_by_id, save_parser_output
from backend.models.single_agent_result import ClaimCheck
from backend.models.parser_output import (
    ActualResult,
    ComparableValuation,
    DemandSignals,
    Financials,
    FlaggedSection,
    FloatDetails,
    FundingHistoryItem,
    KeyPerson,
    FactualClaimEvidence,
    ParserOutput,
    RiskFactorClaimEvidence,
    S1Projection,
)
from backend.models.scenario_output import DeliveryEvidence
from backend.services.agent_run_logger import (
    log_agent_run_completed,
    log_agent_run_failed,
    log_agent_run_start,
)

S1_DISCLOSURE_CHECKLIST_REVENUE_CLAIM_ID = "Revenue growth guidance present?"
S1_DISCLOSURE_CHECKLIST_PROFIT_CLAIM_ID = "Profitability timeline mentioned?"
S1_DISCLOSURE_CHECKLIST_CUSTOMER_CLAIM_ID = "Customer/cohort metrics disclosed?"
S1_DISCLOSURE_CHECKLIST_MARKET_CLAIM_ID = "Explicit CAGR or market-size claim?"
S1_DISCLOSURE_CHECKLIST_RISK_CLAIM_ID = "Red-flag language in Risk Factors?"
S1_DISCLOSURE_CHECKLIST_PROJECTION_CLAIM_ID = "SPAC / merger-deck style projections (heuristic)?"
S1_DISCLOSURE_CHECKLIST_SPARSE_CLAIM_ID = "Sparse disclosure typical of era?"
S1_DISCLOSURE_CHECKLIST_CLAIM_IDS: tuple[str, ...] = (
    S1_DISCLOSURE_CHECKLIST_REVENUE_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_PROFIT_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_CUSTOMER_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_MARKET_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_RISK_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_PROJECTION_CLAIM_ID,
    S1_DISCLOSURE_CHECKLIST_SPARSE_CLAIM_ID,
)


class ProspectusParserInput(BaseModel):
    analysis_id: str


class ProspectusParserResult(BaseModel):
    analysis_id: str


class ProspectusParser:
    _CHECKLIST_REVENUE_LABEL = S1_DISCLOSURE_CHECKLIST_REVENUE_CLAIM_ID
    _CHECKLIST_PROFIT_LABEL = S1_DISCLOSURE_CHECKLIST_PROFIT_CLAIM_ID
    _CHECKLIST_CUSTOMER_LABEL = S1_DISCLOSURE_CHECKLIST_CUSTOMER_CLAIM_ID
    _CHECKLIST_MARKET_LABEL = S1_DISCLOSURE_CHECKLIST_MARKET_CLAIM_ID
    _CHECKLIST_RISK_LABEL = S1_DISCLOSURE_CHECKLIST_RISK_CLAIM_ID
    _CHECKLIST_PROJECTION_LABEL = S1_DISCLOSURE_CHECKLIST_PROJECTION_CLAIM_ID
    _CHECKLIST_SPARSE_LABEL = S1_DISCLOSURE_CHECKLIST_SPARSE_CLAIM_ID

    async def run(self, payload: ProspectusParserInput) -> ProspectusParserResult:
        run_record = await log_agent_run_start(
            analysis_id=payload.analysis_id,
            agent_name="prospectus_parser",
            input_reference=f"analysis_id={payload.analysis_id}",
        )
        run_id: str = str(run_record["id"]) if run_record else ""

        try:
            analysis = await get_analysis_by_id(payload.analysis_id)
            if analysis is None:
                raise RuntimeError(f"Analysis not found for analysis_id={payload.analysis_id}")

            harvester_raw = analysis.get("harvester_output")
            if not isinstance(harvester_raw, dict):
                harvester_raw = {}

            company_name = str(analysis.get("company_name") or harvester_raw.get("company_name") or "").strip()
            parser_output = self._parse_harvester_output(company_name=company_name, harvester_output=harvester_raw)
            await save_parser_output(
                analysis_id=payload.analysis_id,
                output=parser_output.model_dump(mode="json"),
            )
        except Exception as exc:
            await log_agent_run_failed(run_id=run_id, error_message=str(exc))
            raise

        await log_agent_run_completed(
            run_id=run_id,
            output_reference=f"analysis_id={payload.analysis_id}",
        )
        return ProspectusParserResult(analysis_id=payload.analysis_id)

    @staticmethod
    def _is_prospectus_filing_type(filing_type: str) -> bool:
        u = filing_type.upper().strip()
        return u in ("S-1", "S-1/A", "F-1", "424B4")

    @staticmethod
    def _is_prospectus_filing_type_loose(filing_type: str) -> bool:
        if ProspectusParser._is_prospectus_filing_type(filing_type):
            return True
        s = filing_type.strip().upper()
        pad = f" {s} "
        if re.search(r"[^0-9A-Z]S-1(?:/A)?(?:[^0-9A-Z]|$)", pad):
            return True
        if re.search(r"[^0-9A-Z]F-1(?:/A)?(?:[^0-9A-Z]|$)", pad):
            return True
        compact = re.sub(r"\s+", "", s)
        return "424B4" in compact

    @staticmethod
    def _is_10k_filing_type(filing_type: str) -> bool:
        u = filing_type.upper().strip()
        return u.startswith("10-K")

    def _first_filing_text(
        self,
        filings: list[Any],
        predicate: Callable[[str], bool],
    ) -> str:
        for item in filings:
            if not isinstance(item, dict):
                continue
            ft = str(item.get("filing_type") or "")
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            if predicate(ft):
                return text
        return ""

    def parse_10k_actuals(self, filing_text: str) -> list[ActualResult]:
        if not filing_text.strip():
            return []

        results: list[ActualResult] = []
        financial_window = self._locate_financial_statements_section(filing_text) or filing_text
        revenue = self._extract_money_after_keywords(
            financial_window,
            ("revenue", "total revenue", "net revenue"),
            min_value=1_000,
            max_value=1e12,
        )
        if revenue is not None:
            results.append(
                ActualResult(
                    metric="revenue",
                    actual_value=revenue,
                    source_filing="10-K",
                    source_section="financial_statements",
                )
            )

        cash_flow_source = financial_window
        burn_rate: float | None = None
        for keyword in (
            "cash used in operating activities",
            "cash used in operations",
            "operating cash flow",
            "burn rate",
        ):
            keyword_lc = keyword.lower()
            idx = cash_flow_source.lower().find(keyword_lc)
            if idx < 0:
                continue
            start = max(0, idx - 160)
            end = min(len(cash_flow_source), idx + 320)
            window = cash_flow_source[start:end]
            amount = self._extract_money_after_keywords(
                window,
                (keyword,),
                min_value=1_000,
                max_value=1e11,
            )
            if amount is None:
                continue
            window_lc = window.lower()
            if any(token in window_lc for token in ("per month", "monthly", "/month")):
                factor = 1
            elif any(
                token in window_lc
                for token in (
                    "per year",
                    "annual",
                    "per annum",
                    "for the year",
                    "twelve months",
                    "year ended",
                    "for fiscal year",
                )
            ):
                factor = 12
            elif "six months" in window_lc:
                factor = 6
            elif "nine months" in window_lc:
                factor = 9
            elif "three months" in window_lc or "quarter" in window_lc:
                factor = 3
            else:
                factor = 1
            burn_rate = amount / factor
            break
        if burn_rate is None:
            burn_rate = self._extract_money_after_keywords(
                cash_flow_source,
                (
                    "burn rate",
                    "cash used in operating activities",
                    "cash used in operations",
                    "operating cash flow",
                ),
                min_value=1_000,
                max_value=1e11,
            )
        if burn_rate is not None:
            results.append(
                ActualResult(
                    metric="burn_rate",
                    actual_value=burn_rate,
                    source_filing="10-K",
                    source_section="mda",
                )
            )

        risk_section = self._locate_10k_risk_section(filing_text) or ""
        if risk_section:

            def _is_noise(s: str) -> bool:
                if re.search(r"table of contents", s, re.IGNORECASE):
                    return True
                if re.search(r"^page\s+\d", s, re.IGNORECASE):
                    return True
                if re.search(r"investing in our .+ involves risks", s, re.IGNORECASE):
                    return True
                if re.search(r"^[A-Z][A-Z\s&,\.]+$", s):
                    return True
                return False

            risk_count = 0
            for sentence in re.split(r"(?<=[.!?])\s+", risk_section):
                if risk_count >= 5:
                    break
                cleaned = sentence.strip()
                lower = cleaned.lower()
                if len(cleaned) < 60:
                    continue
                if "risk" in lower or "uncertain" in lower or "adverse" in lower:
                    if _is_noise(cleaned):
                        continue
                    if cleaned.count(" ") < 8:
                        continue
                    risk_count += 1
                    results.append(
                        ActualResult(
                            metric=f"risk_factor_{risk_count}",
                            actual_value=None,
                            source_filing="10-K",
                            source_section="risk_factors",
                        )
                    )
        return results

    def compare_s1_to_10k(
        self,
        s1_projections: list[S1Projection],
        actuals: list[ActualResult],
    ) -> list[DeliveryEvidence]:
        actual_by_metric: dict[str, float | None] = {}
        for row in actuals:
            key = self._normalize_metric_key(row.metric)
            if key not in actual_by_metric:
                actual_by_metric[key] = row.actual_value

        out: list[DeliveryEvidence] = []
        for proj in s1_projections:
            key = self._normalize_metric_key(proj.metric)
            actual_val = actual_by_metric.get(key)
            if proj.s1_value is None or actual_val is None:
                continue
            if not key.startswith("risk_factor"):
                tol = max(1e-6, abs(proj.s1_value) * 0.001)
                if abs(actual_val - proj.s1_value) <= tol:
                    verdict: Literal["met", "missed", "exceeded"] = "met"
                elif actual_val < proj.s1_value:
                    verdict = "missed"
                else:
                    verdict = "exceeded"
                claim_s = f"{proj.metric} S-1 projection: {proj.s1_value}"
                actual_s = f"{proj.metric} 10-K actual: {actual_val}"
                out.append(DeliveryEvidence(claim=claim_s, actual=actual_s, verdict=verdict))
        return out

    def _public_record_era_appendix(
        self,
        ipo_date: date | None,
        yahoo_finance_data: dict[str, Any] | None,
        ticker: str | None,
    ) -> str:
        msg = (
            "Pre-2000 UK/US prospectuses often exposed only lock-up and share-count basics in the public record "
            "we can access here; revenue or metric guidance may not appear in the EDGAR extract for that context."
        )
        if ipo_date is not None and ipo_date.year < 2000:
            return msg
        y = yahoo_finance_data or {}
        country = str(y.get("country") or "").lower().strip()
        ex = str(y.get("exchange") or "").lower()
        if "united kingdom" in country or country in ("gb", "uk"):
            return msg
        if "london" in ex or re.search(r"\blse\b", ex) or "lseg" in ex:
            return msg
        t = (ticker or "").strip().upper()
        if t.endswith(".L") or t.endswith(".LN"):
            return msg
        return ""

    def _missing_prospectus_body_rationale(
        self,
        ipo_date: date | None,
        yahoo_finance_data: dict[str, Any] | None,
        ticker: str | None,
    ) -> str:
        base = "No S-1, F-1, or 424B4 prospectus body text was returned from SEC EDGAR in this tool run."
        era = self._public_record_era_appendix(ipo_date, yahoo_finance_data, ticker)
        return f"{base} {era}".strip() if era else base

    def _build_projection_mechanism_claim(
        self,
        filing_text: str,
        confidence: Literal["high", "medium", "low"],
    ) -> ClaimCheck:
        lt = filing_text.lower()
        strong = bool(
            re.search(r"\b(?:special purpose acquisition|de-?spac)\b", lt)
            or re.search(r"\bspac\b", lt)
            or re.search(r"\b(?:business combination|investor presentation)\b", lt)
            or re.search(r"\bpipe\b", lt)
        )
        direct = bool(
            re.search(r"\b(?:direct listing|direct\s+public\s+offering)\b", lt) or re.search(r"\bdpo\b", lt)
        )
        mixedish = bool(re.search(r"\b(?:pro forma|illustrative|redemption|warrants?|founder shares|sponsor)\b", lt))
        status: Literal["supported", "missed", "mixed", "unverifiable"]
        rationale: str | None
        if strong and direct:
            status = "mixed"
            rationale = (
                "Both SPAC or merger-style language and direct-listing style language appear in this extract "
                "(heuristic only)."
            )
        elif strong:
            status = "supported"
            rationale = (
                "Language points to SPAC, merger presentation, or similar non-plain-IPO framing in this extract "
                "(heuristic only; does not attribute projections beyond the text returned)."
            )
        elif direct:
            status = "mixed"
            rationale = (
                "Direct-listing or DPO-style language appears; projection framing may differ from a classic "
                "firm-commitment S-1 (heuristic only)."
            )
        elif mixedish:
            status = "mixed"
            rationale = (
                "Some merger-, SPAC-, or deck-style wording appears but is not decisive on this extract (heuristic only)."
            )
        else:
            status = "missed"
            rationale = (
                "No decisive SPAC, merger-deck, direct-listing, or similar projection-framing signal in the "
                "available prospectus text (heuristic only)."
            )
        quote = self._find_sentence_matching(
            filing_text,
            (
                "special purpose acquisition",
                "spac",
                "de-spac",
                "business combination",
                "investor presentation",
                "direct listing",
                "pipe",
                "founder shares",
                "sponsor",
                "pro forma",
            ),
            require_numeric=False,
        )
        return ClaimCheck(
            claim_id=self._CHECKLIST_PROJECTION_LABEL,
            status=status,
            evidence_quotes=[quote] if quote else [],
            rationale=rationale,
            matched_facts=["projection_source_heuristic"] if status == "supported" else [],
            confidence=confidence,
        )

    def build_s1_disclosure_checklist(
        self,
        parser_output: dict[str, Any],
        filing_text: str,
        *,
        ipo_date: date | None = None,
        yahoo_finance_data: dict[str, Any] | None = None,
        ticker: str | None = None,
    ) -> list[ClaimCheck]:
        data_confidence = str(parser_output.get("data_confidence") or "medium").lower()
        confidence: Literal["high", "medium", "low"] = "medium"
        if data_confidence in ("high", "medium", "low"):
            confidence = data_confidence

        if not filing_text.strip():
            unavailable = self._missing_prospectus_body_rationale(ipo_date, yahoo_finance_data, ticker)
            era = self._public_record_era_appendix(ipo_date, yahoo_finance_data, ticker)
            sparse_sparse_rationale = (
                "No prospectus body text in this run; this row stays visible so sparse-era disclosure is not "
                "conflated with a retrieved prospectus that is merely thin."
            )
            if era:
                sparse_sparse_rationale = f"{sparse_sparse_rationale} {era}"
            projection_rationale = (
                "Heuristic projection-source scan needs S-1, F-1, or 424B4 body text from the current SEC extract."
            )
            if era:
                projection_rationale = f"{projection_rationale} {era}"
            return [
                ClaimCheck(claim_id=self._CHECKLIST_REVENUE_LABEL, status="unverifiable", rationale=unavailable, confidence=confidence),
                ClaimCheck(claim_id=self._CHECKLIST_PROFIT_LABEL, status="unverifiable", rationale=unavailable, confidence=confidence),
                ClaimCheck(claim_id=self._CHECKLIST_CUSTOMER_LABEL, status="unverifiable", rationale=unavailable, confidence=confidence),
                ClaimCheck(claim_id=self._CHECKLIST_MARKET_LABEL, status="unverifiable", rationale=unavailable, confidence=confidence),
                ClaimCheck(claim_id=self._CHECKLIST_RISK_LABEL, status="unverifiable", rationale=unavailable, confidence=confidence),
                ClaimCheck(
                    claim_id=self._CHECKLIST_PROJECTION_LABEL,
                    status="unverifiable",
                    rationale=projection_rationale,
                    confidence=confidence,
                ),
                ClaimCheck(
                    claim_id=self._CHECKLIST_SPARSE_LABEL,
                    status="mixed",
                    rationale=sparse_sparse_rationale,
                    confidence=confidence,
                ),
            ]

        financials = parser_output.get("financials")
        financials_dict = financials if isinstance(financials, dict) else {}
        revenue_quote = self._quote_from_nested_evidence(financials_dict, "revenue_growth_yoy_evidence")
        revenue_sentence = revenue_quote or self._find_sentence(
            filing_text,
            ("year-over-year growth", "yoy growth", "revenue growth", "grow revenue", "increase revenue"),
        )
        revenue_check = ClaimCheck(
            claim_id=self._CHECKLIST_REVENUE_LABEL,
            status="supported" if revenue_sentence else "missed",
            evidence_quotes=[revenue_sentence] if revenue_sentence else [],
            rationale=None if revenue_sentence else "No explicit revenue growth guidance found in the filing text.",
            matched_facts=["revenue_growth_yoy"] if revenue_sentence else [],
            confidence=confidence,
        )

        profitability_sentence = self._find_sentence_matching(
            filing_text,
            (
                "profitability",
                "profitable",
                "break-even",
                "breakeven",
                "positive cash flow",
                "operating margin",
            ),
        )
        profitability_has_timing = bool(
            profitability_sentence
            and re.search(
                r"\b(?:20\d{2}|19\d{2}|within\s+\d+\s+(?:months|years)|next\s+\d+\s+(?:months|years)|by\s+(?:the\s+end\s+of\s+)?(?:20\d{2}|19\d{2}|q[1-4]))\b",
                profitability_sentence,
                flags=re.IGNORECASE,
            )
        )
        profitability_status: Literal["supported", "missed", "mixed", "unverifiable"]
        profitability_rationale: str | None = None
        if profitability_sentence and profitability_has_timing:
            profitability_status = "supported"
        elif profitability_sentence:
            profitability_status = "mixed"
            profitability_rationale = "Profitability is mentioned, but the filing does not give a concrete timeline."
        else:
            profitability_status = "missed"
            profitability_rationale = "No explicit profitability timeline found in the filing text."
        profitability_check = ClaimCheck(
            claim_id=self._CHECKLIST_PROFIT_LABEL,
            status=profitability_status,
            evidence_quotes=[profitability_sentence] if profitability_sentence else [],
            rationale=profitability_rationale,
            matched_facts=["profitability_timeline"] if profitability_sentence else [],
            confidence=confidence,
        )

        customer_sentence = self._find_sentence_matching(
            filing_text,
            (
                "customer",
                "customers",
                "retention",
                "cohort",
                "churn",
                "arpu",
                "ltv",
                "cac",
                "bookings",
                "active users",
                "monthly active users",
                "daily active users",
                "net revenue retention",
            ),
            require_numeric=True,
        )
        customer_check = ClaimCheck(
            claim_id=self._CHECKLIST_CUSTOMER_LABEL,
            status="supported" if customer_sentence else "missed",
            evidence_quotes=[customer_sentence] if customer_sentence else [],
            rationale=None if customer_sentence else "No concrete customer or cohort metric was found in the filing text.",
            matched_facts=["customer_metrics"] if customer_sentence else [],
            confidence=confidence,
        )

        market_sentence = self._find_sentence_matching(
            filing_text,
            (
                "cagr",
                "compound annual growth",
                "total addressable market",
                "tam",
                "sam",
                "som",
                "market opportunity",
                "addressable market",
                "market size",
            ),
            require_numeric=True,
        )
        market_check = ClaimCheck(
            claim_id=self._CHECKLIST_MARKET_LABEL,
            status="supported" if market_sentence else "missed",
            evidence_quotes=[market_sentence] if market_sentence else [],
            rationale=None if market_sentence else "No explicit CAGR or market-size claim was found in the filing text.",
            matched_facts=["market_size_claim"] if market_sentence else [],
            confidence=confidence,
        )

        risk_evidence = parser_output.get("risk_factors_evidence")
        risk_evidence_list = risk_evidence if isinstance(risk_evidence, list) else []
        red_flag_quote: str | None = None
        red_flag_pattern = re.compile(
            r"\b(?:material weakness|going concern|substantial doubt|limited operating history|history of losses|never achieved profitability|customer concentration|single customer|dependence on|adversely affect|uncertain|liquidity|litigation|regulatory)\b",
            flags=re.IGNORECASE,
        )
        for item in risk_evidence_list:
            if not isinstance(item, dict):
                continue
            quote = str(item.get("quote") or item.get("risk_factor") or "").strip()
            if quote and red_flag_pattern.search(quote):
                red_flag_quote = quote
                break
        risk_factors = parser_output.get("risk_factors")
        risk_factor_list = risk_factors if isinstance(risk_factors, list) else []
        risk_status: Literal["supported", "missed", "mixed", "unverifiable"]
        risk_rationale: str | None = None
        if red_flag_quote:
            risk_status = "supported"
        elif risk_factor_list:
            risk_status = "missed"
            risk_rationale = "Risk factors are present, but no strong red-flag phrase matched the checklist."
        else:
            risk_status = "missed"
            risk_rationale = "No usable risk-factor disclosure was found in the filing text."
        risk_check = ClaimCheck(
            claim_id=self._CHECKLIST_RISK_LABEL,
            status=risk_status,
            evidence_quotes=[red_flag_quote] if red_flag_quote else [],
            rationale=risk_rationale,
            matched_facts=["risk_factors"] if red_flag_quote else [],
            confidence=confidence,
        )

        sparse_hits = sum(
            1
            for status in (
                revenue_check.status,
                profitability_check.status,
                customer_check.status,
                market_check.status,
            )
            if status == "supported"
        )
        demand_signals = parser_output.get("demand_signals")
        demand_signals_dict = demand_signals if isinstance(demand_signals, dict) else {}
        institutional_interest = str(demand_signals_dict.get("institutional_interest") or "").strip().lower()
        roadshow_sentiment = str(demand_signals_dict.get("roadshow_sentiment") or "").strip()
        has_demand_signal = institutional_interest not in {"", "unknown"} or (
            roadshow_sentiment and roadshow_sentiment != "No clear roadshow sentiment found."
        )
        use_of_proceeds = str(parser_output.get("use_of_proceeds") or "").strip()
        has_use_of_proceeds = bool(
            use_of_proceeds
            and "not clearly identified" not in use_of_proceeds.lower()
            and "unavailable" not in use_of_proceeds.lower()
            and "preliminary" not in use_of_proceeds.lower()
        )
        business_model = str(parser_output.get("business_model") or "").strip()
        has_business_model = bool(
            business_model
            and business_model != "Business model summary not clearly stated in available filing text."
            and business_model != "Preliminary analysis. S-1 filing not available."
        )
        float_details = parser_output.get("float_details")
        float_details_dict = float_details if isinstance(float_details, dict) else {}
        has_basic_structure = bool(
            self._to_float(float_details_dict.get("total_shares_offered"))
            or self._to_float(float_details_dict.get("public_float"))
            or self._to_float(parser_output.get("lockup_period_days"))
        )
        sparse_quote = self._find_sentence_matching(
            filing_text,
            ("lock-up", "lock up", "shares offered", "public float", "lockup"),
        )
        sparse_status: Literal["supported", "missed", "mixed", "unverifiable"] = (
            "supported"
            if has_basic_structure and sparse_hits == 0 and not has_demand_signal and not has_use_of_proceeds and not has_business_model
            else "missed"
        )
        sparse_rationale = (
            "Sparse disclosure typical of era — only lock-up and basic share count were clearly disclosed."
            if sparse_status == "supported"
            else "Disclosure goes beyond bare lock-up and share-count basics (modern-style detail present)."
        )
        sparse_check = ClaimCheck(
            claim_id=self._CHECKLIST_SPARSE_LABEL,
            status=sparse_status,
            evidence_quotes=[sparse_quote] if sparse_quote else [],
            rationale=sparse_rationale,
            matched_facts=["lockup_period_days", "float_details"] if sparse_status == "supported" else [],
            confidence=confidence,
        )

        projection_check = self._build_projection_mechanism_claim(filing_text, confidence)

        return [
            revenue_check,
            profitability_check,
            customer_check,
            market_check,
            risk_check,
            projection_check,
            sparse_check,
        ]

    @staticmethod
    def _normalize_metric_key(metric: str) -> str:
        return metric.strip().lower().replace(" ", "_")

    def _build_s1_projections_from_s1_text(self, s1_text: str) -> list[S1Projection]:
        if not s1_text.strip():
            return []
        temp_flags: list[FlaggedSection] = []
        fin = self._extract_financials(s1_text, temp_flags)
        projections: list[S1Projection] = []
        if fin.revenue is not None:
            projections.append(
                S1Projection(
                    metric="revenue",
                    s1_value=fin.revenue,
                    s1_context="Extracted from S-1 financial statements section",
                )
            )
        if fin.burn_rate_monthly is not None:
            projections.append(
                S1Projection(
                    metric="burn_rate",
                    s1_value=fin.burn_rate_monthly,
                    s1_context="Extracted from S-1 cash flow / operating activities",
                )
            )
        return projections

    def _locate_10k_risk_section(self, text: str) -> str | None:
        if not text:
            return None
        lowered = text.lower()
        for needle in ("item 1a", "item 1a.", "risk factors"):
            idx = lowered.find(needle)
            if idx >= 0:
                start = max(idx - 2000, 0)
                end = min(idx + 25000, len(text))
                chunk = text[start:end].strip()
                if chunk:
                    return chunk
        return self._locate_risk_factors_section(text)

    def _parse_harvester_output(self, company_name: str, harvester_output: dict[str, Any]) -> ParserOutput:
        sec_filings = harvester_output.get("sec_filings")
        filings = sec_filings if isinstance(sec_filings, list) else []
        filing_texts = [str(item.get("text") or "") for item in filings if isinstance(item, dict)]
        merged_text = " ".join(text for text in filing_texts if text).strip()
        s1_text = self._first_filing_text(filings, self._is_prospectus_filing_type)
        ten_k_text = self._first_filing_text(filings, self._is_10k_filing_type)
        news_context = self._merge_news_context(harvester_output.get("news_articles"))
        narrative_text = merged_text or news_context

        flagged_sections: list[FlaggedSection] = []
        if not merged_text:
            flagged_sections.append(
                FlaggedSection(
                    section="S-1 filing",
                    reason="No filing text available from SEC EDGAR",
                    verify_at="harvester_output.sec_filings",
                )
            )

        financials = self._extract_financials(merged_text, flagged_sections)
        risk_factors, risk_factors_evidence = self._extract_risk_factors(narrative_text)
        use_of_proceeds, use_of_proceeds_evidence = self._extract_use_of_proceeds(
            merged_text, flagged_sections
        )
        key_people = self._extract_key_people(narrative_text)
        lockup_period_days = self._extract_lockup_days(merged_text, flagged_sections)
        float_details = self._extract_float_details(merged_text, flagged_sections)
        insider_selling_percentage = self._extract_insider_selling(merged_text)
        offering_type = self._classify_offering_type(narrative_text, insider_selling_percentage)

        yahoo_data = harvester_output.get("yahoo_finance_data")
        comparable_valuations = self._extract_comparable_valuations(yahoo_data)

        crunchbase_data = harvester_output.get("crunchbase_data")
        funding_history = self._extract_funding_history(crunchbase_data, flagged_sections)
        demand_signals = self._extract_demand_signals(narrative_text, crunchbase_data, harvester_output)

        data_confidence = self._derive_confidence(merged_text, news_context, financials, flagged_sections)
        business_model = self._extract_business_model(narrative_text)

        s1_projections = self._build_s1_projections_from_s1_text(s1_text or merged_text)
        actuals: list[ActualResult] = []
        has_post_ipo_10k = False
        if ten_k_text:
            has_post_ipo_10k = True
            actuals = self.parse_10k_actuals(ten_k_text)
            self.compare_s1_to_10k(s1_projections, actuals)

        return ParserOutput(
            company_name=company_name or "unknown",
            business_model=business_model,
            financials=financials,
            risk_factors=risk_factors,
            risk_factors_evidence=risk_factors_evidence,
            use_of_proceeds=use_of_proceeds,
            use_of_proceeds_evidence=use_of_proceeds_evidence,
            key_people=key_people,
            comparable_valuations=comparable_valuations,
            lockup_period_days=lockup_period_days,
            float_details=float_details,
            demand_signals=demand_signals,
            funding_history=funding_history,
            offering_type=offering_type,
            insider_selling_percentage=insider_selling_percentage,
            s1_projections=s1_projections,
            actuals=actuals,
            has_post_ipo_10k=has_post_ipo_10k,
            parsed_at=datetime.now(timezone.utc),
            data_confidence=data_confidence,
            flagged_sections=flagged_sections,
        )

    def _split_filing_into_sections(self, text: str) -> dict[str, str]:
        if not text:
            return {}

        anchors: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("cover_page", ("prospectus", "cover page")),
            ("prospectus_summary", ("prospectus summary", "summary")),
            ("risk_factors", ("risk factors",)),
            ("use_of_proceeds", ("use of proceeds", "use of the net proceeds")),
            ("business", ("business", "our business")),
            ("management", ("management", "directors and executive officers")),
            ("principal_and_selling_stockholders", ("principal and selling stockholders", "selling stockholders")),
            ("financial_statements", ("financial statements", "selected financial data", "management’s discussion")),
            ("underwriting", ("underwriting",)),
        )

        matches: list[tuple[int, str]] = []
        lowered = text.lower()
        for section_key, phrases in anchors:
            for phrase in phrases:
                idx = lowered.find(phrase)
                if idx >= 0:
                    matches.append((idx, section_key))
                    break

        if not matches:
            return {"full_text": text}

        matches.sort(key=lambda item: item[0])
        deduped: list[tuple[int, str]] = []
        seen_keys: set[str] = set()
        for idx, key in matches:
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append((idx, key))

        sections: dict[str, str] = {}
        for i, (start, key) in enumerate(deduped):
            end = deduped[i + 1][0] if i + 1 < len(deduped) else len(text)
            chunk = text[start:end].strip()
            if chunk:
                sections[key] = chunk
        return sections

    def _locate_cover_page_section(self, text: str) -> str | None:
        if not text:
            return None

        sections = self._split_filing_into_sections(text)
        cover = sections.get("cover_page")
        if cover:
            return cover

        lowered = text.lower()
        prospectus_idx = lowered.find("prospectus")
        if prospectus_idx >= 0:
            start = max(prospectus_idx - 4000, 0)
            end = min(prospectus_idx + 12000, len(text))
            chunk = text[start:end].strip()
            return chunk or None

        chunk = text[:12000].strip()
        return chunk or None

    def _locate_use_of_proceeds_section(self, text: str) -> str | None:
        if not text:
            return None

        sections = self._split_filing_into_sections(text)
        use_of_proceeds = sections.get("use_of_proceeds")
        if use_of_proceeds:
            return use_of_proceeds

        lowered = text.lower()
        idx = lowered.find("use of proceeds")
        if idx < 0:
            idx = lowered.find("use of the net proceeds")
        if idx < 0:
            idx = lowered.find("we intend to use the net proceeds")
        if idx < 0:
            return None

        start = max(idx - 6000, 0)
        end = min(idx + 18000, len(text))
        chunk = text[start:end].strip()
        return chunk or None

    def _locate_risk_factors_section(self, text: str) -> str | None:
        if not text:
            return None

        sections = self._split_filing_into_sections(text)
        risk_factors = sections.get("risk_factors")
        if risk_factors:
            return risk_factors

        lowered = text.lower()
        idx = lowered.find("risk factors")
        if idx < 0:
            return None

        start = max(idx - 6000, 0)
        end = min(idx + 24000, len(text))
        chunk = text[start:end].strip()
        return chunk or None

    def _locate_principal_and_selling_stockholders_section(self, text: str) -> str | None:
        if not text:
            return None

        sections = self._split_filing_into_sections(text)
        stockholders = sections.get("principal_and_selling_stockholders")
        if stockholders:
            return stockholders

        lowered = text.lower()
        idx = lowered.find("principal and selling stockholders")
        if idx < 0:
            idx = lowered.find("selling stockholders")
        if idx < 0:
            return None

        start = max(idx - 6000, 0)
        end = min(idx + 24000, len(text))
        chunk = text[start:end].strip()
        return chunk or None

    def _locate_financial_statements_section(self, text: str) -> str | None:
        if not text:
            return None

        sections = self._split_filing_into_sections(text)
        financials = sections.get("financial_statements")
        if financials:
            return financials

        lowered = text.lower()
        idx = lowered.find("financial statements")
        if idx < 0:
            idx = lowered.find("selected financial data")
        if idx < 0:
            idx = lowered.find("management’s discussion")
        if idx < 0:
            idx = lowered.find("management's discussion")
        if idx < 0:
            return None

        start = max(idx - 8000, 0)
        end = min(idx + 32000, len(text))
        chunk = text[start:end].strip()
        return chunk or None

    def _extract_business_model(self, text: str) -> str:
        if not text:
            return "Preliminary analysis. S-1 filing not available."
        match = self._find_sentence(text, ("business model", "our platform", "we provide", "our business"))
        return match or "Business model summary not clearly stated in available filing text."

    def _extract_financials(self, text: str, flags: list[FlaggedSection]) -> Financials:
        financial_statements_candidate = self._locate_financial_statements_section(text)
        revenue_source_text = financial_statements_candidate or text
        cash_flow_source_text = financial_statements_candidate or text
        balance_sheet_source_text = financial_statements_candidate or text
        revenue = self._extract_money_after_keywords(
            revenue_source_text,
            ("revenue", "total revenue", "net revenue"),
            min_value=1_000,
            max_value=1e12,
        )
        revenue_evidence = None
        if revenue is not None:
            revenue_quote = self._find_sentence(
                revenue_source_text,
                ("revenue", "total revenue", "net revenue"),
            )
            revenue_evidence = FactualClaimEvidence(
                source="SEC EDGAR",
                source_reference="SEC EDGAR S-1 — financial statements section",
                quote=revenue_quote,
                extracted_at=datetime.now(timezone.utc),
            )
        burn_rate: float | None = None
        for keyword in (
            "cash used in operating activities",
            "cash used in operations",
            "operating cash flow",
            "burn rate",
        ):
            keyword_lc = keyword.lower()
            idx = cash_flow_source_text.lower().find(keyword_lc)
            if idx < 0:
                continue

            start = max(0, idx - 160)
            end = min(len(cash_flow_source_text), idx + 320)
            window = cash_flow_source_text[start:end]

            amount = self._extract_money_after_keywords(
                window,
                (keyword,),
                min_value=1_000,
                max_value=1e11,
            )
            if amount is None:
                continue

            window_lc = window.lower()
            if any(token in window_lc for token in ("per month", "monthly", "/month")):
                factor = 1
            elif any(
                token in window_lc
                for token in (
                    "per year",
                    "annual",
                    "per annum",
                    "for the year",
                    "twelve months",
                    "year ended",
                    "for fiscal year",
                )
            ):
                factor = 12
            elif "six months" in window_lc:
                factor = 6
            elif "nine months" in window_lc:
                factor = 9
            elif "three months" in window_lc or "quarter" in window_lc:
                factor = 3
            else:
                # If we cannot reliably infer the reporting period, assume the statement already
                # provides a monthly cash-use figure.
                factor = 1

            burn_rate = amount / factor
            break

        if burn_rate is None:
            # Fallback to legacy extraction (best-effort).
            burn_rate = self._extract_money_after_keywords(
                cash_flow_source_text,
                (
                    "burn rate",
                    "cash used in operating activities",
                    "cash used in operations",
                    "operating cash flow",
                ),
                min_value=1_000,
                max_value=1e11,
            )
        burn_rate_evidence = None
        if burn_rate is not None:
            burn_quote = self._find_sentence(
                cash_flow_source_text,
                (
                    "burn rate",
                    "cash used in operating activities",
                    "cash used in operations",
                    "operating cash flow",
                ),
            )
            burn_rate_evidence = FactualClaimEvidence(
                source="SEC EDGAR",
                source_reference="SEC EDGAR S-1 — cash flow / operating activities",
                quote=burn_quote,
                extracted_at=datetime.now(timezone.utc),
            )

        cash_balance = self._extract_money_after_keywords(
            balance_sheet_source_text,
            (
                "cash and cash equivalents",
                "cash and cash equivalents at",
                "cash and cash equivalents were",
                "cash and cash equivalents, net",
            ),
            min_value=1_000,
            max_value=1e12,
        )
        cash_balance_quote = None
        if cash_balance is not None:
            cash_balance_quote = self._find_sentence(
                balance_sheet_source_text,
                ("cash and cash equivalents",),
            )

        runway_direct = self._extract_number_after_keywords(
            text,
            ("cash runway", "runway", "months of cash"),
        )
        runway_direct_quote = None
        if runway_direct is not None:
            runway_direct_quote = self._find_sentence(
                text,
                ("cash runway", "months of cash", "runway"),
            )

        runway: float | None = None
        runway_evidence = None
        if cash_balance is not None and burn_rate is not None and burn_rate > 0:
            runway = cash_balance / burn_rate
            runway_evidence = FactualClaimEvidence(
                source="SEC EDGAR",
                source_reference=(
                    "SEC EDGAR S-1 — cash and cash equivalents; computed runway from burn_rate_monthly"
                ),
                quote=cash_balance_quote,
                extracted_at=datetime.now(timezone.utc),
            )
        else:
            runway = runway_direct
            if runway_direct is not None:
                runway_evidence = FactualClaimEvidence(
                    source="SEC EDGAR",
                    source_reference="SEC EDGAR S-1 — cash runway disclosure",
                    quote=runway_direct_quote,
                    extracted_at=datetime.now(timezone.utc),
                )
        growth = self._extract_percentage_after_keywords(
            revenue_source_text,
            ("year-over-year growth", "yoy growth", "revenue growth"),
        )
        growth_evidence = None
        if growth is not None:
            growth_quote = self._find_sentence(
                revenue_source_text,
                ("year-over-year growth", "yoy growth", "revenue growth"),
            )
            growth_evidence = FactualClaimEvidence(
                source="SEC EDGAR",
                source_reference="SEC EDGAR S-1 — financial statements section",
                quote=growth_quote,
                extracted_at=datetime.now(timezone.utc),
            )

        if revenue is None:
            flags.append(
                FlaggedSection(
                    section="Financials",
                    reason="Revenue metric missing from filing text",
                    verify_at="SEC EDGAR S-1 financial statements",
                )
            )
        if burn_rate is None:
            flags.append(
                FlaggedSection(
                    section="Financials",
                    reason="Burn rate metric missing from filing text",
                    verify_at="SEC EDGAR cash flow section",
                )
            )

        return Financials(
            revenue=revenue,
            revenue_evidence=revenue_evidence,
            revenue_growth_yoy=growth,
            revenue_growth_yoy_evidence=growth_evidence,
            burn_rate_monthly=burn_rate,
            burn_rate_monthly_evidence=burn_rate_evidence,
            cash_runway_months=runway,
            cash_runway_months_evidence=runway_evidence,
        )

    def _extract_risk_factors(
        self, text: str
    ) -> tuple[list[str], list[RiskFactorClaimEvidence]]:
        if not text:
            return [], []

        risk_section_text = self._locate_risk_factors_section(text) or text

        def _is_noise(s: str) -> bool:
            if re.search(r"table of contents", s, re.IGNORECASE):
                return True
            if re.search(r"^page\s+\d", s, re.IGNORECASE):
                return True
            if re.search(r"investing in our .+ involves risks", s, re.IGNORECASE):
                return True
            if re.search(r"^[A-Z][A-Z\s&,\.]+$", s):
                return True
            return False

        candidates: list[str] = []
        evidence: list[RiskFactorClaimEvidence] = []
        for sentence in re.split(r"(?<=[.!?])\s+", risk_section_text):
            cleaned = sentence.strip()
            lower = cleaned.lower()
            if len(cleaned) < 60:
                continue
            if "risk" in lower or "uncertain" in lower or "adverse" in lower:
                if _is_noise(cleaned):
                    continue
                if cleaned.count(" ") < 8:
                    continue
                candidate = cleaned[:400]
                candidates.append(candidate)
                evidence.append(
                    RiskFactorClaimEvidence(
                        risk_factor=candidate,
                        source="SEC EDGAR",
                        source_reference="SEC EDGAR S-1 — Risk Factors section",
                        quote=candidate,
                        extracted_at=datetime.now(timezone.utc),
                    )
                )
            if len(candidates) >= 10:
                break
        return candidates, evidence

    def _extract_use_of_proceeds(
        self, text: str, flags: list[FlaggedSection]
    ) -> tuple[str, FactualClaimEvidence | None]:
        if not text:
            flags.append(
                FlaggedSection(
                    section="Use of Proceeds",
                    reason="No filing text available",
                    verify_at="SEC EDGAR S-1 use of proceeds section",
                )
            )
            return ("Preliminary. Use of proceeds unavailable without filing text.", None)

        candidate_text = self._locate_use_of_proceeds_section(text) or text
        sentence = self._find_sentence(
            candidate_text,
            (
                "use of proceeds",
                "we intend to use the net proceeds",
                "proceeds from this offering",
            ),
        )
        if sentence:
            return (
                sentence,
                FactualClaimEvidence(
                    source="SEC EDGAR",
                    source_reference="SEC EDGAR S-1 — use of proceeds section",
                    quote=sentence,
                    extracted_at=datetime.now(timezone.utc),
                ),
            )

        fallback_sentence = self._find_sentence(
            text,
            (
                "use of proceeds",
                "we intend to use the net proceeds",
                "proceeds from this offering",
            ),
        )
        if fallback_sentence:
            return (
                fallback_sentence,
                FactualClaimEvidence(
                    source="SEC EDGAR",
                    source_reference="SEC EDGAR S-1 — fallback statement from merged filing text",
                    quote=fallback_sentence,
                    extracted_at=datetime.now(timezone.utc),
                ),
            )

        flags.append(
            FlaggedSection(
                section="Use of Proceeds",
                reason="Could not identify explicit use-of-proceeds statement",
                verify_at="SEC EDGAR S-1 use of proceeds section",
            )
        )
        return ("Use of proceeds statement not clearly identified in available filing text.", None)

    def _extract_key_people(self, text: str) -> list[KeyPerson]:
        if not text:
            return []
        patterns = (
            (r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2}),?\s+(?:our\s+)?Chief Executive Officer", "CEO"),
            (r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2}),?\s+(?:our\s+)?Chief Financial Officer", "CFO"),
            (r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2}),?\s+(?:our\s+)?Chair(?:man|person)", "Chair"),
        )
        seen: set[str] = set()
        output: list[KeyPerson] = []
        for pattern, role in patterns:
            for match in re.finditer(pattern, text):
                name = match.group(1).strip()
                if name in seen:
                    continue
                seen.add(name)
                output.append(KeyPerson(name=name, role=role, background="From filing leadership disclosure"))
                if len(output) >= 8:
                    return output
        return output

    def _extract_comparable_valuations(self, yahoo_data: Any) -> list[ComparableValuation]:
        if not isinstance(yahoo_data, dict):
            return []
        comparables = yahoo_data.get("comparable_companies")
        multiples = yahoo_data.get("sector_multiples")
        if not isinstance(comparables, list) or not isinstance(multiples, dict):
            return []

        valuation_rows: list[ComparableValuation] = []
        metric_map = (
            ("trailing_pe_median", "Trailing P/E"),
            ("forward_pe_median", "Forward P/E"),
            ("price_to_sales_median", "Price/Sales"),
            ("price_to_book_median", "Price/Book"),
        )
        lead_company = str(comparables[0]) if comparables else "sector_peer_set"
        for key, label in metric_map:
            value = multiples.get(key)
            parsed = self._to_float(value)
            if parsed is None:
                continue
            valuation_rows.append(ComparableValuation(company=lead_company, metric=label, value=parsed))
        return valuation_rows

    def _extract_lockup_days(self, text: str, flags: list[FlaggedSection]) -> int:
        if not text:
            flags.append(
                FlaggedSection(
                    section="Lock-up",
                    reason="No filing text available to detect lock-up period",
                    verify_at="SEC EDGAR underwriting section",
                )
            )
            return 180

        sections = self._split_filing_into_sections(text)
        underwriting_candidate = sections.get("underwriting")
        if underwriting_candidate:
            match = re.search(
                r"(\d{2,3})\s*day(?:s)?\s+lock[- ]?up",
                underwriting_candidate,
                flags=re.IGNORECASE,
            )
            if match:
                return int(match.group(1))

        match = re.search(
            r"(\d{2,3})\s*day(?:s)?\s+lock[- ]?up",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            return int(match.group(1))
        return 180

    def _extract_float_details(self, text: str, flags: list[FlaggedSection]) -> FloatDetails:
        sections = self._split_filing_into_sections(text)
        cover_candidate = self._locate_cover_page_section(text)
        underwriting_candidate = sections.get("underwriting")

        candidate_texts: list[str] = []
        if cover_candidate:
            candidate_texts.append(cover_candidate)
        if underwriting_candidate:
            candidate_texts.append(underwriting_candidate)

        total: float | None = None
        for candidate in candidate_texts:
            total = self._extract_number_after_keywords(
                candidate,
                ("shares offered", "total shares", "shares to be sold"),
            )
            if total is not None:
                break
        if total is None:
            total = self._extract_number_after_keywords(
                text,
                ("shares offered", "total shares", "shares to be sold"),
            )
        insider = self._extract_number_after_keywords(
            text,
            ("shares by existing stockholders", "shares sold by existing", "insider shares"),
        )
        public_float: float | None = None
        for candidate in (underwriting_candidate, cover_candidate):
            if not candidate:
                continue
            public_float = self._extract_number_after_keywords(
                candidate,
                ("public float", "shares outstanding available for trading"),
            )
            if public_float is not None:
                break
        if public_float is None:
            public_float = self._extract_number_after_keywords(
                text,
                ("public float", "shares outstanding available for trading"),
            )
        greenshoe = bool(re.search(r"(over[- ]allotment|greenshoe)", text, flags=re.IGNORECASE))

        if total is None:
            flags.append(
                FlaggedSection(
                    section="Float Details",
                    reason="Total shares offered not clearly found",
                    verify_at="SEC EDGAR cover page and underwriting section",
                )
            )
        safe_total = total or 0.0
        safe_insider = insider or 0.0
        safe_public = public_float if public_float is not None else max(safe_total - safe_insider, 0.0)
        return FloatDetails(
            total_shares_offered=safe_total,
            insider_shares=safe_insider,
            public_float=safe_public,
            greenshoe_option=greenshoe,
        )

    def _extract_demand_signals(self, text: str, crunchbase_data: Any, harvester_output: dict[str, Any]) -> DemandSignals:
        anchors: list[str] = []
        if isinstance(crunchbase_data, dict):
            investors = crunchbase_data.get("investors")
            if isinstance(investors, list):
                anchors = [str(name).strip() for name in investors if str(name).strip()][:5]

        lower_text = text.lower()
        institutional_interest: str = "unknown"
        if "strong institutional" in lower_text or "oversubscribed" in lower_text:
            institutional_interest = "high"
        elif "institutional interest" in lower_text:
            institutional_interest = "medium"
        elif "weak demand" in lower_text:
            institutional_interest = "low"

        roadshow_sentiment = self._find_sentence(text, ("roadshow", "book-building", "investor demand")) or "No clear roadshow sentiment found."
        if institutional_interest == "unknown":
            twitter = harvester_output.get("twitter_data")
            if isinstance(twitter, dict):
                sentiment = twitter.get("sentiment_score")
                if isinstance(sentiment, dict):
                    pos = self._to_float(sentiment.get("positive")) or 0.0
                    neg = self._to_float(sentiment.get("negative")) or 0.0
                    if pos - neg > 0.2:
                        institutional_interest = "high"
                    elif neg - pos > 0.2:
                        institutional_interest = "low"
                    else:
                        institutional_interest = "medium"

        return DemandSignals(
            anchor_investors=anchors,
            institutional_interest=institutional_interest,
            roadshow_sentiment=roadshow_sentiment,
        )

    def _extract_funding_history(
        self,
        crunchbase_data: Any,
        flags: list[FlaggedSection],
    ) -> list[FundingHistoryItem]:
        if not isinstance(crunchbase_data, dict):
            flags.append(
                FlaggedSection(
                    section="Funding History",
                    reason="Crunchbase data unavailable",
                    verify_at="harvester_output.crunchbase_data",
                )
            )
            return []

        rounds = crunchbase_data.get("funding_rounds")
        if not isinstance(rounds, list):
            return []

        output: list[FundingHistoryItem] = []
        for item in rounds:
            if not isinstance(item, dict):
                continue
            amount = self._to_float(item.get("amount"))
            date = self._to_datetime(item.get("date"))
            if amount is None or date is None:
                continue
            investors_raw = item.get("investors")
            investors = [str(value).strip() for value in investors_raw] if isinstance(investors_raw, list) else []
            output.append(
                FundingHistoryItem(
                    round=str(item.get("round") or "unknown"),
                    amount=amount,
                    date=date,
                    investors=[name for name in investors if name],
                    valuation=self._to_float(item.get("valuation")),
                )
            )
        return output

    def _extract_insider_selling(self, text: str) -> float | None:
        if not text:
            return None

        section_candidate = self._locate_principal_and_selling_stockholders_section(text) or text

        match = re.search(
            r"(?:(?:insider|existing stockholder|selling stockholder)s?)[\w\s]{0,250}?"
            r"(?:will\s+sell|intend\s+to\s+sell|are\s+selling|sell)?\s*"
            r"(\d{1,3}(?:\.\d+)?)\s*%",
            section_candidate,
            flags=re.IGNORECASE,
        )
        if match:
            return float(match.group(1))

        match = re.search(
            r"(?:existing stockholder|selling stockholder|insider).{0,250}?(?:percent|%)[\w\s]{0,20}?"
            r"(\d{1,3}(?:\.\d+)?)\s*%",
            section_candidate,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return None
        return float(match.group(1))

    def _classify_offering_type(
        self,
        text: str,
        insider_selling_percentage: float | None,
    ) -> Literal["primary", "secondary", "mixed"]:
        lower = text.lower()
        if "secondary offering" in lower:
            return "secondary"
        if "primary offering" in lower:
            return "primary"
        if insider_selling_percentage is not None and insider_selling_percentage > 0:
            return "mixed"
        return "primary"

    def _derive_confidence(
        self,
        filing_text: str,
        news_text: str,
        financials: Financials,
        flags: list[FlaggedSection],
    ) -> Literal["high", "medium", "low"]:
        if not filing_text and not news_text:
            return "low"
        if not filing_text and news_text:
            if financials.revenue is not None or financials.burn_rate_monthly is not None:
                return "medium"
            return "low"
        missing_core = sum(
            1
            for value in (
                financials.revenue,
                financials.burn_rate_monthly,
                financials.cash_runway_months,
            )
            if value is None
        )
        if missing_core >= 2 or len(flags) >= 6:
            return "low"
        if missing_core == 1 or len(flags) >= 3:
            return "medium"
        return "high"

    def _merge_news_context(self, news_articles: Any) -> str:
        if not isinstance(news_articles, list):
            return ""
        parts: list[str] = []
        for article in news_articles[:12]:
            if not isinstance(article, dict):
                continue
            title = str(article.get("title") or "").strip()
            content = str(article.get("content") or "").strip()
            block = " ".join(part for part in (title, content) if part)
            if block:
                parts.append(block)
        return " ".join(parts).strip()

    def _extract_money_after_keywords(
        self,
        text: str,
        keywords: tuple[str, ...],
        *,
        require_scale: bool = False,
        min_value: float = 0,
        max_value: float = 1e12,
    ) -> float | None:
        for keyword in keywords:
            pattern = rf"{re.escape(keyword)}[\w\s,:\-]{{0,40}}?\$?\s*(\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)\s*(million|billion|thousand|m|b|k)?"
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            value = self._to_float(match.group(1))
            if value is None:
                continue
            scale = str(match.group(2) or "").lower()
            if scale in ("billion", "b"):
                value *= 1_000_000_000
            elif scale in ("million", "m"):
                value *= 1_000_000
            elif scale in ("thousand", "k"):
                value *= 1_000
            elif require_scale:
                continue
            if value < min_value or value > max_value:
                continue
            return value
        return None

    def _extract_number_after_keywords(self, text: str, keywords: tuple[str, ...]) -> float | None:
        for keyword in keywords:
            pattern = rf"{re.escape(keyword)}[\w\s,:\-]{{0,25}}?(\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)"
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            parsed = self._to_float(match.group(1))
            if parsed is not None:
                return parsed
        return None

    def _extract_percentage_after_keywords(self, text: str, keywords: tuple[str, ...]) -> float | None:
        for keyword in keywords:
            pattern = rf"{re.escape(keyword)}[\w\s,:\-]{{0,20}}?(\d{{1,3}}(?:\.\d+)?)\s*%"
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            return self._to_float(match.group(1))
        return None

    def _find_sentence(self, text: str, keywords: tuple[str, ...]) -> str | None:
        if not text:
            return None
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            stripped = sentence.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if any(keyword in lower for keyword in keywords):
                return stripped[:600]
        return None

    def _find_sentence_matching(
        self,
        text: str,
        keywords: tuple[str, ...],
        *,
        require_numeric: bool = False,
    ) -> str | None:
        if not text:
            return None
        numeric_pattern = re.compile(r"\b(?:\d{1,3}(?:,\d{3})*(?:\.\d+)?%?|\$\d{1,3}(?:,\d{3})*(?:\.\d+)?(?:\s*(?:million|billion|thousand|m|b|k))?)\b", re.IGNORECASE)
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            stripped = sentence.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if not any(keyword in lower for keyword in keywords):
                continue
            if require_numeric and not numeric_pattern.search(stripped):
                continue
            return stripped[:600]
        return None

    def _quote_from_nested_evidence(self, payload: dict[str, Any], key: str) -> str | None:
        raw = payload.get(key)
        if not isinstance(raw, dict):
            return None
        quote = str(raw.get("quote") or "").strip()
        return quote or None

    def _to_datetime(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

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
