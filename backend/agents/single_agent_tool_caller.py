import logging
from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel

from backend.agents.data_harvester import DataHarvester, DataHarvesterInput
from backend.agents.prospectus_parser import ProspectusParser, ProspectusParserInput
from backend.agents.scenario_builder import ScenarioBuilder, ScenarioBuilderInput
from backend.database.queries import (
    get_analysis_by_id,
    save_final_report,
    set_analysis_active_sources,
    set_analysis_complexity_tier,
    set_analysis_ticker_and_ipo_date,
)
from backend.models.single_agent_result import (
    FilingFact,
    OutcomeMetrics,
    PredictionClaim,
    SingleAgentResult,
    ClaimCheck,
)
from backend.agents.narrative_synthesiser import NarrativeSynthesiser
from backend.models.scenario_output import PatternFlag
from backend.services.news_claim_extractor import extract_news_derived_claims
from backend.services.news_filing_discrepancy import (
    build_news_filing_discrepancies,
    first_primary_filing_text,
)
from backend.services.agent_run_logger import (
    log_agent_run_completed,
    log_agent_run_failed,
    log_agent_run_start,
)
from backend.services.reference_output_contract import (
    build_output_contract_bundle,
    outcome_metrics_has_core_price_signal,
)
from backend.tools.sec_edgar_client import fetch_sec_edgar, resolve_ticker_from_input
from backend.tools.newsapi_client import fetch_news_api
from backend.tools.rss_client import fetch_rss_feeds
from backend.tools.yfinance_client import (
    fetch_ipo_price_history,
    resolve_ipo_date_for_ticker,
    fetch_yahoo_finance,
)
from backend.tools.crunchbase_client import fetch_crunchbase
from backend.tools.fred_client import fetch_fred_data
from backend.tools.twitter_client import fetch_twitter

logger = logging.getLogger(__name__)


class SingleAgentToolCallerInput(BaseModel):
    analysis_id: str


def _coerce_analysis_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _first_s1_url(analysis: dict[str, Any]) -> str | None:
    harvester_output = analysis.get("harvester_output")
    if not isinstance(harvester_output, dict):
        return None
    sec_filings = harvester_output.get("sec_filings")
    if not isinstance(sec_filings, list):
        return None
    for filing in sec_filings:
        if not isinstance(filing, dict):
            continue
        filing_type = str(filing.get("filing_type") or "")
        if ProspectusParser._is_prospectus_filing_type_loose(filing_type):
            url = filing.get("url")
            if isinstance(url, str) and url.strip():
                return url.strip()
    for filing in sec_filings:
        if not isinstance(filing, dict):
            continue
        url = filing.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    return None


def _first_s1_text(analysis: dict[str, Any]) -> str:
    harvester_output = analysis.get("harvester_output")
    if not isinstance(harvester_output, dict):
        return ""
    sec_filings = harvester_output.get("sec_filings")
    if not isinstance(sec_filings, list):
        return ""
    for filing in sec_filings:
        if not isinstance(filing, dict):
            continue
        filing_type = str(filing.get("filing_type") or "")
        if not ProspectusParser._is_prospectus_filing_type_loose(filing_type):
            continue
        text = str(filing.get("text") or "").strip()
        if text:
            return text
    return ""


def _prediction_claims_from_parser(parser_output: dict[str, Any], source_url: str | None) -> list[PredictionClaim]:
    claims: list[PredictionClaim] = []
    financials = parser_output.get("financials")
    if isinstance(financials, dict):
        revenue = financials.get("revenue")
        if isinstance(revenue, (int, float)):
            claims.append(
                PredictionClaim(
                    claim_id="s1_revenue_growth",
                    claim_type="growth",
                    prediction_text=f"S-1 projected revenue about {revenue:,.0f}.",
                    source="SEC EDGAR",
                    source_url=source_url,
                )
            )
        burn = financials.get("burn_rate_monthly")
        if isinstance(burn, (int, float)):
            claims.append(
                PredictionClaim(
                    claim_id="s1_burn_rate",
                    claim_type="burn",
                    prediction_text=f"S-1 projected monthly burn about {burn:,.0f}.",
                    source="SEC EDGAR",
                    source_url=source_url,
                )
            )
        runway = financials.get("cash_runway_months")
        if isinstance(runway, (int, float)):
            claims.append(
                PredictionClaim(
                    claim_id="s1_cash_runway",
                    claim_type="runway",
                    prediction_text=f"S-1 projected cash runway around {runway:.1f} months.",
                    source="SEC EDGAR",
                    source_url=source_url,
                )
            )
    lockup_days = parser_output.get("lockup_period_days")
    if isinstance(lockup_days, (int, float)) and lockup_days > 0:
        claims.append(
            PredictionClaim(
                claim_id="s1_lockup",
                claim_type="lockup",
                prediction_text=f"S-1 disclosed an insider lock-up period of about {int(lockup_days)} days.",
                source="SEC EDGAR",
                source_url=source_url,
            )
        )
    insider_pct = parser_output.get("insider_selling_percentage")
    if isinstance(insider_pct, (int, float)) and insider_pct > 0:
        claims.append(
            PredictionClaim(
                claim_id="s1_insider_selling",
                claim_type="insider_selling",
                prediction_text=f"S-1 disclosed insider selling around {insider_pct:.1f}% (of relevant float).",
                source="SEC EDGAR",
                source_url=source_url,
            )
        )
    demand_signals = parser_output.get("demand_signals")
    if isinstance(demand_signals, dict):
        institutional_interest = demand_signals.get("institutional_interest")
        roadshow_sentiment = demand_signals.get("roadshow_sentiment")
        txt_parts: list[str] = []
        if isinstance(institutional_interest, str) and institutional_interest.strip():
            txt_parts.append(f"Institutional interest: {institutional_interest}.")
        if isinstance(roadshow_sentiment, str) and roadshow_sentiment.strip():
            txt_parts.append(roadshow_sentiment.strip())
        if txt_parts:
            claims.append(
                PredictionClaim(
                    claim_id="s1_demand_signals",
                    claim_type="demand",
                    prediction_text=" ".join(txt_parts)[:700],
                    source="SEC EDGAR",
                    source_url=source_url,
                )
            )
    return claims


def _filing_facts_from_parser(parser_output: dict[str, Any], source_url: str | None) -> list[FilingFact]:
    facts: list[FilingFact] = []
    financials = parser_output.get("financials")
    if isinstance(financials, dict):
        for metric, key in (
            ("revenue", "revenue"),
            ("revenue_growth_yoy", "revenue_growth_yoy"),
            ("burn_rate_monthly", "burn_rate_monthly"),
            ("cash_runway_months", "cash_runway_months"),
        ):
            val = financials.get(key)
            v = float(val) if isinstance(val, (int, float)) else None
            facts.append(
                FilingFact(
                    fact_id=f"fact_{key}",
                    metric=metric,
                    value=v,
                    units=None,
                    source="s1_f1",
                    source_reference=key,
                    source_url=source_url,
                )
            )
    lockup_days = parser_output.get("lockup_period_days")
    if isinstance(lockup_days, (int, float)):
        facts.append(
            FilingFact(
                fact_id="fact_lockup_period_days",
                metric="lockup_period_days",
                value=float(lockup_days),
                units="days",
                source="s1_f1",
                source_reference="lockup_period_days",
                source_url=source_url,
            )
        )
    float_details = parser_output.get("float_details")
    if isinstance(float_details, dict):
        for metric, key, unit in (
            ("total_shares_offered", "total_shares_offered", "shares"),
            ("insider_shares", "insider_shares", "shares"),
            ("public_float", "public_float", "shares"),
        ):
            val = float_details.get(key)
            v = float(val) if isinstance(val, (int, float)) else None
            facts.append(
                FilingFact(
                    fact_id=f"fact_{key}",
                    metric=metric,
                    value=v,
                    units=unit,
                    source="s1_f1",
                    source_reference=key,
                    source_url=source_url,
                )
            )
    insider_pct = parser_output.get("insider_selling_percentage")
    if isinstance(insider_pct, (int, float)):
        facts.append(
            FilingFact(
                fact_id="fact_insider_selling_percentage",
                metric="insider_selling_percentage",
                value=float(insider_pct),
                units="percent",
                source="s1_f1",
                source_reference="insider_selling_percentage",
                source_url=source_url,
            )
        )
    return facts


def _outcome_metrics_from_scenario(scenario_output: dict[str, Any]) -> OutcomeMetrics | None:
    price_perf = scenario_output.get("price_performance")
    if not isinstance(price_perf, dict):
        if "price_performance" in scenario_output and price_perf is not None:
            logger.warning(
                "scenario_output.price_performance is not a dict (type=%s)",
                type(price_perf).__name__,
            )
        return None
    try:
        outcome = OutcomeMetrics.model_validate(price_perf)
    except Exception:
        logger.warning("scenario_output.price_performance failed validation: %s", price_perf)
        return None
    if not outcome_metrics_has_core_price_signal(outcome):
        logger.warning("price_performance missing core price fields: %s", price_perf)
        return None
    return outcome


def _delivery_claim_checks_from_s1_evidence(
    prediction_claims: list[PredictionClaim],
    scenario_output: dict[str, Any],
    parser_output: dict[str, Any],
) -> list[ClaimCheck]:
    evidence = scenario_output.get("delivery_evidence") or []
    if not isinstance(evidence, list):
        evidence = []
    data_confidence = str(parser_output.get("data_confidence") or "medium").lower()
    default_confidence: Literal["high", "medium", "low"] = "medium"
    if data_confidence in ("high", "medium", "low"):
        default_confidence = data_confidence

    checks: list[ClaimCheck] = []
    evidence_by_type: dict[str, Any] = {}
    for row in evidence:
        if not isinstance(row, dict):
            continue
        claim = str(row.get("claim") or "")
        verdict = str(row.get("verdict") or "")
        actual = str(row.get("actual") or "")
        metric_prefix = claim.split(" S-1 projection")[0].strip().lower()
        evidence_by_type[metric_prefix] = {"verdict": verdict, "claim": claim, "actual": actual}

    for c in prediction_claims:
        status: Literal["supported", "missed", "mixed", "unverifiable"] = "unverifiable"
        matched: list[str] = []
        quotes: list[str] = []
        if c.claim_type == "growth":
            row = evidence_by_type.get("revenue")
            if row:
                verdict = str(row["verdict"])
                status = "supported" if verdict in ("met", "exceeded") else "missed"
                matched = ["revenue"]
                quotes = [str(row["claim"]), str(row["actual"])]
        elif c.claim_type == "burn":
            row = evidence_by_type.get("burn_rate")
            if row:
                verdict = str(row["verdict"])
                status = "supported" if verdict in ("met", "exceeded") else "missed"
                matched = ["burn_rate"]
                quotes = [str(row["claim"]), str(row["actual"])]
        elif c.claim_type in ("runway", "lockup", "insider_selling", "demand", "valuation", "margin"):
            status = "unverifiable"

        checks.append(
            ClaimCheck(
                claim_id=c.claim_id,
                status=status,
                matched_facts=matched,
                evidence_quotes=quotes,
                rationale=None,
                confidence=default_confidence,
            )
        )
    return checks


def _claim_checks_from_s1_evidence(
    parser: ProspectusParser,
    parser_output: dict[str, Any],
    filing_text: str,
    *,
    ipo_date: date | None,
    yahoo_finance_data: dict[str, Any],
    ticker: str | None,
) -> list[ClaimCheck]:
    return parser.build_s1_disclosure_checklist(
        parser_output=parser_output,
        filing_text=filing_text,
        ipo_date=ipo_date,
        yahoo_finance_data=yahoo_finance_data,
        ticker=ticker,
    )


class SingleAgentToolCaller:
    def __init__(self) -> None:
        self._data_harvester = DataHarvester(
            sec_edgar=fetch_sec_edgar,
            rss_feeds=fetch_rss_feeds,
            news_api=fetch_news_api,
            crunchbase=fetch_crunchbase,
            yahoo_finance=fetch_yahoo_finance,
            fred=fetch_fred_data,
            twitter=fetch_twitter,
        )
        self._parser = ProspectusParser()
        self._scenario_builder = ScenarioBuilder()
        self._narrative_synthesiser = NarrativeSynthesiser()

    async def run(self, payload: SingleAgentToolCallerInput) -> dict[str, Any]:
        run_record = await log_agent_run_start(
            analysis_id=payload.analysis_id,
            agent_name="single_agent",
            input_reference=f"analysis_id={payload.analysis_id}",
        )
        run_id = str(run_record["id"]) if run_record else ""
        try:
            analysis = await get_analysis_by_id(payload.analysis_id)
            if analysis is None:
                raise RuntimeError(f"Analysis not found for analysis_id={payload.analysis_id}")
            company_name = str(analysis.get("company_name") or "").strip()
            if not company_name:
                raise RuntimeError(f"Missing company_name for analysis_id={payload.analysis_id}")

            requested_tier = str(analysis.get("complexity_tier") or "standard").strip().lower()
            selected_sources = ["sec_edgar", "rss_feeds", "news_api", "yahoo_finance"]
            selected_tier: str = "simple"
            if requested_tier == "complex":
                selected_tier = "complex"
            elif requested_tier == "standard":
                selected_tier = "standard"

            await set_analysis_complexity_tier(payload.analysis_id, selected_tier)  # type: ignore[arg-type]
            await set_analysis_active_sources(payload.analysis_id, selected_sources)

            ticker = analysis.get("ticker")
            ticker_val = ticker if isinstance(ticker, str) else None
            ticker_norm = ticker_val.strip().upper() if ticker_val and ticker_val.strip() else None
            ipo_date = _coerce_analysis_date(analysis.get("ipo_date"))

            if ticker_norm is None:
                ticker_norm = (await resolve_ticker_from_input(company_name)).strip().upper()
            if ipo_date is None and ticker_norm is not None:
                ipo_date = await resolve_ipo_date_for_ticker(ticker_norm)

            await set_analysis_ticker_and_ipo_date(payload.analysis_id, ticker_norm, ipo_date)

            ipo_price_history: dict[str, Any] | None = None
            if ticker_norm and ipo_date:
                ipo_price_history = await fetch_ipo_price_history(ticker_norm, ipo_date)

            await self._data_harvester.run(
                DataHarvesterInput(
                    analysis_id=payload.analysis_id,
                    company_name=company_name,
                    complexity_tier=selected_tier,  # type: ignore[arg-type]
                    active_sources=selected_sources,
                    ticker=ticker_norm,
                    ipo_date=ipo_date,
                    ipo_price_history=ipo_price_history,
                )
            )
            await self._parser.run(ProspectusParserInput(analysis_id=payload.analysis_id))
            await self._scenario_builder.run(ScenarioBuilderInput(analysis_id=payload.analysis_id))

            fresh = await get_analysis_by_id(payload.analysis_id)
            if fresh is None:
                raise RuntimeError(f"Analysis disappeared for analysis_id={payload.analysis_id}")

            from backend.api.websocket_progress import emit_agent_status

            emit_agent_status(
                analysis_id=payload.analysis_id,
                agent_name="single_agent",
                status="running",
                tool_call="assemble_result",
            )

            harvester_output = fresh.get("harvester_output") or {}
            parser_output = fresh.get("parser_output") or {}
            scenario_output = fresh.get("scenario_output") or {}
            if not isinstance(harvester_output, dict) or not isinstance(parser_output, dict) or not isinstance(scenario_output, dict):
                raise RuntimeError("Expected harvester/parser/scenario outputs to be dictionaries")

            yahoo_raw = harvester_output.get("yahoo_finance_data")
            yahoo_data: dict[str, Any] = yahoo_raw if isinstance(yahoo_raw, dict) else {}

            source_url = _first_s1_url(fresh)
            s1_text = _first_s1_text(fresh)
            prediction_claims = _prediction_claims_from_parser(parser_output=parser_output, source_url=source_url)
            filing_facts = _filing_facts_from_parser(parser_output=parser_output, source_url=source_url)
            outcome_metrics = _outcome_metrics_from_scenario(scenario_output=scenario_output)

            delivery_claim_checks = _delivery_claim_checks_from_s1_evidence(
                prediction_claims=prediction_claims,
                scenario_output=scenario_output,
                parser_output=parser_output,
            )
            claim_checks = _claim_checks_from_s1_evidence(
                parser=self._parser,
                parser_output=parser_output,
                filing_text=s1_text,
                ipo_date=ipo_date,
                yahoo_finance_data=yahoo_data,
                ticker=ticker_norm,
            )

            filing_text = first_primary_filing_text(harvester_output)
            news_derived_claims = extract_news_derived_claims(harvester_output)
            news_filing_discrepancies = build_news_filing_discrepancies(
                news_derived_claims,
                parser_output,
                scenario_output,
                filing_text,
            )

            patterns = scenario_output.get("patterns_flagged") or []
            patterns_out: list[PatternFlag] = []
            if isinstance(patterns, list):
                for p in patterns:
                    try:
                        patterns_out.append(PatternFlag.model_validate(p))
                    except Exception:
                        continue

            comparable_tickers = yahoo_data.get("comparable_companies") if isinstance(yahoo_data.get("comparable_companies"), list) else []

            output_contract = build_output_contract_bundle(
                company_name=company_name,
                ticker=ticker_norm,
                ipo_date=ipo_date,
                parser_output=parser_output,
                scenario_output=scenario_output,
                outcome_metrics=outcome_metrics,
                prediction_claims=prediction_claims,
                claim_checks=delivery_claim_checks,
                patterns_flagged=patterns_out,
                comparable_tickers=[str(item).strip().upper() for item in comparable_tickers if str(item).strip()],
                yahoo_finance_data=yahoo_data,
                s1_disclosure_checks=claim_checks,
                post_ipo_10k=str(harvester_output.get("post_ipo_10k") or "").strip() or None,
            )

            narrative = await self._narrative_synthesiser.synthesise(
                company_name=company_name,
                parser_output=parser_output,
                harvester_output=harvester_output,
                outcome_metrics=outcome_metrics,
                prediction_claims=prediction_claims,
                filing_facts=filing_facts,
            )

            result = SingleAgentResult(
                company_name=company_name,
                generated_at=datetime.now(timezone.utc),
                prediction_claims=prediction_claims,
                filing_facts=filing_facts,
                outcome_metrics=outcome_metrics,
                company_profile=output_contract.company_profile,
                pre_ipo_thesis=output_contract.pre_ipo_thesis,
                realized_outcome=output_contract.realized_outcome,
                pattern_classification=output_contract.pattern_classification,
                reference_table_row=output_contract.reference_table_row,
                claim_checks=claim_checks,
                patterns=patterns_out,
                narrative=narrative,
                news_derived_claims=news_derived_claims,
                news_filing_discrepancies=news_filing_discrepancies,
            )
            await save_final_report(payload.analysis_id, result.model_dump(mode="json"))
        except Exception as exc:
            await log_agent_run_failed(run_id=run_id, error_message=str(exc))
            raise

        await log_agent_run_completed(
            run_id=run_id,
            output_reference=f"analysis_id={payload.analysis_id}, final_report populated",
        )
        return {"analysis_id": payload.analysis_id}

