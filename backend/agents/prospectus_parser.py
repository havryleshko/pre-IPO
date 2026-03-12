import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from backend.database.queries import get_analysis_by_id, save_parser_output
from backend.models.parser_output import (
    ComparableValuation,
    DemandSignals,
    Financials,
    FlaggedSection,
    FloatDetails,
    FundingHistoryItem,
    KeyPerson,
    ParserOutput,
)
from backend.services.agent_run_logger import (
    log_agent_run_completed,
    log_agent_run_failed,
    log_agent_run_start,
)


class ProspectusParserInput(BaseModel):
    analysis_id: str


class ProspectusParserResult(BaseModel):
    analysis_id: str


class ProspectusParser:
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

    def _parse_harvester_output(self, company_name: str, harvester_output: dict[str, Any]) -> ParserOutput:
        sec_filings = harvester_output.get("sec_filings")
        filings = sec_filings if isinstance(sec_filings, list) else []
        filing_texts = [str(item.get("text") or "") for item in filings if isinstance(item, dict)]
        merged_text = " ".join(text for text in filing_texts if text).strip()

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
        risk_factors = self._extract_risk_factors(merged_text)
        use_of_proceeds = self._extract_use_of_proceeds(merged_text, flagged_sections)
        key_people = self._extract_key_people(merged_text)
        lockup_period_days = self._extract_lockup_days(merged_text, flagged_sections)
        float_details = self._extract_float_details(merged_text, flagged_sections)
        insider_selling_percentage = self._extract_insider_selling(merged_text)
        offering_type = self._classify_offering_type(merged_text, insider_selling_percentage)

        yahoo_data = harvester_output.get("yahoo_finance_data")
        comparable_valuations = self._extract_comparable_valuations(yahoo_data)

        crunchbase_data = harvester_output.get("crunchbase_data")
        funding_history = self._extract_funding_history(crunchbase_data, flagged_sections)
        demand_signals = self._extract_demand_signals(merged_text, crunchbase_data, harvester_output)

        data_confidence = self._derive_confidence(merged_text, financials, flagged_sections)
        business_model = self._extract_business_model(merged_text)

        return ParserOutput(
            company_name=company_name or "unknown",
            business_model=business_model,
            financials=financials,
            risk_factors=risk_factors,
            use_of_proceeds=use_of_proceeds,
            key_people=key_people,
            comparable_valuations=comparable_valuations,
            lockup_period_days=lockup_period_days,
            float_details=float_details,
            demand_signals=demand_signals,
            funding_history=funding_history,
            offering_type=offering_type,
            insider_selling_percentage=insider_selling_percentage,
            parsed_at=datetime.now(timezone.utc),
            data_confidence=data_confidence,
            flagged_sections=flagged_sections,
        )

    def _extract_business_model(self, text: str) -> str:
        if not text:
            return "Preliminary analysis. S-1 filing not available."
        match = self._find_sentence(text, ("business model", "our platform", "we provide", "our business"))
        return match or "Business model summary not clearly stated in available filing text."

    def _extract_financials(self, text: str, flags: list[FlaggedSection]) -> Financials:
        revenue = self._extract_money_after_keywords(
            text,
            ("revenue", "total revenue", "net revenue"),
        )
        burn_rate = self._extract_money_after_keywords(
            text,
            ("burn rate", "cash used in operating activities", "cash used in operations", "operating cash flow"),
        )
        runway = self._extract_number_after_keywords(text, ("cash runway", "runway", "months of cash"))
        growth = self._extract_percentage_after_keywords(
            text,
            ("year-over-year growth", "yoy growth", "revenue growth"),
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
            revenue_growth_yoy=growth,
            burn_rate_monthly=burn_rate,
            cash_runway_months=runway,
        )

    def _extract_risk_factors(self, text: str) -> list[str]:
        if not text:
            return []
        candidates: list[str] = []
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            cleaned = sentence.strip()
            lower = cleaned.lower()
            if len(cleaned) < 30:
                continue
            if "risk" in lower or "uncertain" in lower or "adverse" in lower:
                candidates.append(cleaned[:400])
            if len(candidates) >= 10:
                break
        return candidates

    def _extract_use_of_proceeds(self, text: str, flags: list[FlaggedSection]) -> str:
        if not text:
            flags.append(
                FlaggedSection(
                    section="Use of Proceeds",
                    reason="No filing text available",
                    verify_at="SEC EDGAR S-1 use of proceeds section",
                )
            )
            return "Preliminary. Use of proceeds unavailable without filing text."
        sentence = self._find_sentence(text, ("use of proceeds", "we intend to use the net proceeds", "proceeds from this offering"))
        if sentence:
            return sentence
        flags.append(
            FlaggedSection(
                section="Use of Proceeds",
                reason="Could not identify explicit use-of-proceeds statement",
                verify_at="SEC EDGAR S-1 use of proceeds section",
            )
        )
        return "Use of proceeds statement not clearly identified in available filing text."

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
        match = re.search(r"(\d{2,3})\s*day(?:s)?\s+lock[- ]?up", text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
        return 180

    def _extract_float_details(self, text: str, flags: list[FlaggedSection]) -> FloatDetails:
        total = self._extract_number_after_keywords(
            text,
            ("shares offered", "total shares", "shares to be sold"),
        )
        insider = self._extract_number_after_keywords(
            text,
            ("shares by existing stockholders", "shares sold by existing", "insider shares"),
        )
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
        match = re.search(
            r"(?:insider|existing stockholder)[\w\s]{0,40}?(\d{1,3}(?:\.\d+)?)\s*%",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        return float(match.group(1))

    def _classify_offering_type(self, text: str, insider_selling_percentage: float | None) -> str:
        lower = text.lower()
        if "secondary offering" in lower:
            return "secondary"
        if "primary offering" in lower:
            return "primary"
        if insider_selling_percentage is not None and insider_selling_percentage > 0:
            return "mixed"
        return "primary"

    def _derive_confidence(self, text: str, financials: Financials, flags: list[FlaggedSection]) -> str:
        if not text:
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

    def _extract_money_after_keywords(self, text: str, keywords: tuple[str, ...]) -> float | None:
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
