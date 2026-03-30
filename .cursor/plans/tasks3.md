# Tasks v3.0 — IPO Retrospective Analyser

One task per conversation. Backend before frontend. Models before agents.

---

## Phase 1 — DB Schema

**T301** `backend/database/migrations/003_add_ticker_ipo_date.sql`
Add `ticker VARCHAR(20)` and `ipo_date DATE` to `analyses` table. Done when migration runs cleanly on fresh `docker-compose up`.

**T302** `backend/database/queries.py`
Add `set_analysis_ticker_and_ipo_date(analysis_id, ticker, ipo_date)`.

**T303** `backend/database/queries.py`
Add `get_analysis_ticker_and_ipo_date(analysis_id)`.

---

## Phase 2 — Data Tools

**T304** `backend/tools/sec_edgar_client.py`
Add `fetch_post_ipo_filings(ticker, ipo_date)` — queries EDGAR for 10-K and 10-Q filed after `ipo_date`, returns first 10-K text. Done when ARM ticker + Sep 2023 returns first 10-K text.

**T305** `backend/tools/sec_edgar_client.py`
Add `resolve_ticker_from_name(company_name)` — queries EDGAR company search to resolve ticker. Done when "Arm Holdings" returns "ARM"; mismatched issuer raises a safe error.

**T306** `backend/tools/yfinance_client.py`
Add `fetch_ipo_price_history(ticker, ipo_date)` — returns ipo_price, current_price, peak_price, trough_price, performance_since_ipo_pct, lock_up_cliff_date (ipo_date + 180d), price_at_lock_up_cliff. Done when ARM + Sep 2023 returns all fields.

**T307** `tests/tools/test_sec_edgar_client.py`
Unit tests for `fetch_post_ipo_filings` (mock EDGAR) and `resolve_ticker_from_name` (ARM, RDDT, CART fixtures).

**T308** `tests/tools/test_yfinance_client.py`
Unit tests for `fetch_ipo_price_history`: normal case, post-lock-up cliff drop, company < 12 months post-IPO (no 10-K yet).

---

## Phase 3 — Models

**T309** `backend/models/parser_output.py`
Add `S1Projection` model: `metric: str, s1_value: float | None, s1_context: str`.

**T310** `backend/models/parser_output.py`
Add `ActualResult` model: `metric: str, actual_value: float | None, source_filing: str, source_section: str`.

**T311** `backend/models/parser_output.py`
Add `s1_projections: list[S1Projection]`, `actuals: list[ActualResult]`, `has_post_ipo_10k: bool` to parser output model. Existing tests must still pass.

**T312** `backend/models/scenario_output.py`
Add `DeliveryEvidence` (claim, actual, verdict: met/missed/exceeded), `PricePerformance` (all price fields), `PatternFlag` (signal, was_visible_at_ipo, outcome) models.

**T313** `backend/models/scenario_output.py`
Add `ipo_delivery_verdict`, `delivery_score`, `delivery_evidence`, `price_performance`, `patterns_flagged` to scenario output model. Existing tests must still pass.

**T314** `backend/models/investor_brief.py`
Add `ipo_verdict`, `current_positioning`, `ipo_price`, `current_price`, `performance_since_ipo_pct` to investor brief model. Existing tests must still pass.

---

## Phase 4 — Prospectus Parser

**T315** `backend/agents/prospectus_parser.py`
Add `parse_10k_actuals(filing_text)` — section-aware extraction of revenue, burn rate, top-5 risk factors from 10-K. Done when ARM 10-K fixture returns `ActualResult` list with at least revenue and burn_rate.

**T316** `backend/agents/prospectus_parser.py`
Add `compare_s1_to_10k(s1_projections, actuals)` — matches by metric name, returns `list[DeliveryEvidence]` with met/missed/exceeded per metric. Done when S-1 $3B vs 10-K $2.4B returns `missed`.

**T317** `backend/agents/prospectus_parser.py`
Wire `parse_10k_actuals` and `compare_s1_to_10k` into main `parse` method. Runs only when harvester output contains 10-K text. Sets `has_post_ipo_10k = True`.

**T318** `tests/agents/test_prospectus_parser.py`
Tests for `parse_10k_actuals` (ARM 10-K fixture) and `compare_s1_to_10k` (met/missed/exceeded cases).

---

## Phase 5 — Scenario Builder

**T319** `backend/agents/scenario_builder.py`
Add `compute_delivery_score(delivery_evidence, price_performance)` — rules engine scoring 0-100. ARM-like inputs score ≥65 → "delivered". CART-like inputs score ≤40 → "underdelivered".

**T320** `backend/agents/scenario_builder.py`
Add `detect_ipo_patterns(parser_output, price_performance)` — identifies signals visible at IPO time: insider selling + lock-up cliff drop, burn rate inaccuracy, anchor investor flag. Returns `list[PatternFlag]`.

**T321** `backend/agents/scenario_builder.py`
Update forward scenario generation: use `current_price` as baseline, single 12-month horizon (replacing 3-horizon). Probability sum must equal 100%.

**T322** `backend/agents/scenario_builder.py`
Wire `compute_delivery_score`, `detect_ipo_patterns`, and updated forward scenarios into main `build` method. Writes full updated output to DB.

**T323** `tests/agents/test_scenario_builder.py`
Tests for `compute_delivery_score` (delivered/underdelivered/mixed thresholds), `detect_ipo_patterns` (lock-up cliff pattern), forward scenario baseline using current_price.

---

## Phase 6 — Investor Brief Synthesizer

**T324** `backend/agents/investor_brief_synthesizer.py`
Update LLM prompt for retrospective output: ipo_verdict statement, s1_vs_reality section (3-4 bullet comparison), patterns_flagged narrative, current_positioning section. Pass `delivery_evidence` and `price_performance` into prompt context.

**T325** `backend/agents/investor_brief_synthesizer.py`
Populate `ipo_verdict`, `current_positioning`, `ipo_price`, `current_price`, `performance_since_ipo_pct` directly from scenario_output (deterministic — no LLM).

**T326** `tests/agents/test_investor_brief_synthesizer.py`
Tests: deterministic fields populated correctly from scenario_output, prompt context includes delivery_evidence when available.

---

## Phase 7 — Recommendation Engine

**T327** `backend/models/recommendation_output.py`
Add `RecommendationOutput` model: `decision: Literal["buy","hold","avoid"]`, `decision_scope`, `entry_triggers`, `watch_triggers`, `kill_criteria`, `sizing_guidance`, `decision_rationale`, `decision_evidence`.

**T328** `backend/agents/recommendation_engine.py`
Add `build_decision(delivery_score, current_positioning, parser_output)` — score ≥65 + buy positioning → "buy"; 40-64 → "hold"; <40 or low confidence → "hold". Low parser confidence always degrades to "hold".

**T329** `backend/agents/recommendation_engine.py`
Add `build_entry_triggers(scenario_output, parser_output)` — 2-3 concrete triggers grounded in actual data values (e.g. "Revenue growth sustains >20% YoY in next 10-Q").

**T330** `backend/agents/recommendation_engine.py`
Add `build_kill_criteria(scenario_output, parser_output)` — 2-3 explicit invalidators. Low-confidence parser always adds "Await first 10-K before entry".

**T331** `backend/agents/recommendation_engine.py`
Wire `build_decision`, `build_entry_triggers`, `build_kill_criteria` into main `run` method. Write `RecommendationOutput` to `analyses.recommendation_output`.

**T332** `tests/agents/test_recommendation_engine.py`
Tests: low-confidence downgrade to "hold", private backer cannot become buyable vehicle, no "buy" on score <40, triggers and kill criteria always present.

---

## Phase 8 — Judge Agent

**T333** `backend/agents/judge_agent.py`
Add `validate_recommendation(recommendation_output, parser_output)` — checks: valid decision enum, buy requires score ≥65 + parser confidence not "low", entry_triggers and kill_criteria non-empty, decision_rationale non-empty. Returns `JudgeResult(passed, flags)`.

**T334** `backend/agents/judge_agent.py`
Add `validate_brief(investor_brief)` — checks: ipo_verdict present, overview_markdown ≥200 chars, s1_vs_reality present when `has_post_ipo_10k=True`, references non-empty. Returns `JudgeResult`.

**T335** `backend/agents/judge_agent.py`
Wire `validate_recommendation` and `validate_brief` into main `run` method. Write combined `JudgeResult` to `analyses.judge_output`. Populate `analyses.flags` from failed validations.

**T336** `tests/agents/test_judge_agent.py`
Tests: invalid decision enum rejected, low-confidence buy rejected, missing triggers rejected, missing brief sections rejected.

---

## Phase 9 — Pipeline Wiring

**T337** `backend/services/pipeline_runner.py`
Add pre-harvest step: call `resolve_ticker_from_name` and `fetch_ipo_price_history`, persist ticker + ipo_date to DB via T302. Pass ipo_date and ticker into harvester input.

**T338** `backend/services/pipeline_runner.py`
Wire `recommendation_engine` as pipeline step after `investor_brief_synthesizer`.

**T339** `backend/services/pipeline_runner.py`
Wire `judge_agent` as final pipeline step. On judge failure: set status `completed_with_flags`, populate `analyses.flags`.

**T340** `backend/agents/data_harvester.py`
Add `fetch_post_ipo_filings` call using ticker + ipo_date from harvester input. Store under `post_ipo_10k` key. Null-safe when no 10-K exists.

---

## Phase 10 — Frontend

**T341** `frontend/src/components/InvestorBriefPanel.tsx`
Add `react-markdown` dependency. Replace raw string rendering of `overview_markdown` with `<ReactMarkdown>`.

**T342** `frontend/src/components/VerdictPanel.tsx` (new)
Verdict badge (Delivered / Underdelivered / Mixed), positioning badge (Buy / Hold / Avoid), IPO price → current price → % change row. Null-safe.

**T343** `frontend/src/components/PatternsPanel.tsx` (new)
Render `patterns_flagged`: signal, "visible at IPO" indicator, outcome. Collapses if empty.

**T344** `frontend/src/api/client.ts`
Add `ipo_verdict`, `current_positioning`, `ipo_price`, `current_price`, `performance_since_ipo_pct`, `patterns_flagged` to `InvestorBrief` type. Add `RecommendationOutput` type.

**T345** `frontend/src/App.tsx`
Fix layout to 30/70 split. Wire `VerdictPanel` and `PatternsPanel` above `InvestorBriefPanel`. Add collapsible recommendation section (decision + triggers + kill criteria).

---

## Phase 11 — Tests + Demo

**T346** `tests/integration/test_analysis_end_to_end.py`
End-to-end test: ARM fixture — full pipeline runs, all 7 DB output fields populated, delivery verdict = "delivered", recommendation present.

**T347** `tests/integration/test_analysis_end_to_end.py`
End-to-end test: CART fixture — delivery verdict = "underdelivered", recommendation = "avoid" or "hold".

**T348** `backend/scripts/seed_demo_data.py`
Seed ARM, RDDT, CART with fixture data. Idempotent. Run once after `docker-compose up`.

---

## Execution Order

```
T301 → T302 → T303
T304 → T305 → T306 → T307 → T308
T309 → T310 → T311 → T312 → T313 → T314
T315 → T316 → T317 → T318
T319 → T320 → T321 → T322 → T323
T324 → T325 → T326
T327 → T328 → T329 → T330 → T331 → T332
T333 → T334 → T335 → T336
T337 → T338 → T339 → T340
T341 → T342 → T343 → T344 → T345
T346 → T347 → T348
```
