# Investor Value Tasks

## Objective
Turn the product from a polished IPO narrative prototype into a constrained investor decision tool that can reliably output:
- `buy | watch | avoid`
- a verified tradable vehicle, if one exists
- explicit entry triggers
- explicit kill criteria
- evidence-backed rationale

## Execution Rules
- Complete exactly one task per worker conversation.
- Keep tasks file-scoped whenever possible.
- Backend contract before frontend.
- Validation before presentation.
- Every task ends with focused tests for that task only.
- If a schema task breaks downstream code, fix only the minimum needed to keep the contract consistent.

## Phase 1: Data Reliability

### T201
**File:** `backend/services/pipeline_runner.py`  
**Scope:** Add a helper that derives pre-harvest complexity hints from the analysis input and current record state.

**Done when:**
- `_data_harvester_executor()` no longer builds `ComplexityClassifierInput` with only `company_name`
- hint derivation is isolated in a helper, not inlined

### T202
**File:** `backend/services/pipeline_runner.py`  
**Scope:** Wire the derived hints into `ComplexityClassifierInput` inside `_data_harvester_executor()`.

**Done when:**
- the live pipeline passes meaningful values for classifier hints
- the live path no longer silently behaves like the simple tier for obvious IPOs

### T203
**File:** `backend/database/queries.py`  
**Scope:** Add or extend query support to persist the actual complexity tier selected at runtime.

**Done when:**
- the analysis record can store the true execution tier used by the harvester path

### T204
**File:** `backend/database/queries.py`  
**Scope:** Add or extend query support to persist the actual active source list selected at runtime.

**Done when:**
- the analysis record can store the exact sources used by the live run

### T205
**File:** `backend/services/pipeline_runner.py`  
**Scope:** Save actual complexity tier and active source list after classification and before harvester execution.

**Done when:**
- downstream analysis fetches can inspect the real chosen tier and sources

### T206
**File:** `tests/integration/test_analysis_end_to_end.py`  
**Scope:** Add an integration test asserting the live pipeline persists the chosen complexity tier.

### T207
**File:** `tests/integration/test_analysis_end_to_end.py`  
**Scope:** Add an integration test asserting the live pipeline persists the chosen active source list.

### T208
**File:** `backend/tools/sec_edgar_client.py`  
**Scope:** Add a helper that normalizes and compares requested company name vs resolved SEC issuer name.

**Done when:**
- issuer-match logic is explicit and reusable

### T209
**File:** `backend/tools/sec_edgar_client.py`  
**Scope:** Enforce issuer verification after document resolution and before returning filing data.

**Done when:**
- mismatched issuers are rejected with a safe failure path

### T210
**File:** `tests/tools/test_sec_edgar_client.py`  
**Scope:** Add unit tests for issuer-name matching helper behavior.

### T211
**File:** `tests/tools/test_sec_edgar_client.py`  
**Scope:** Add unit tests for issuer mismatch rejection after filing resolution.

## Phase 2: Parser Foundations

### T212
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Add a helper to split filing text into targeted sections using headings or anchors.

### T213
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Add a cover-page section locator helper.

### T214
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Add a `Use of Proceeds` section locator helper.

### T215
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Add a `Risk Factors` section locator helper.

### T216
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Add a `Principal and Selling Stockholders` section locator helper.

### T217
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Add a financial-statements section locator helper.

### T218
**File:** `backend/models/parser_output.py`  
**Scope:** Add a structured evidence model for extracted factual claims.

### T219
**File:** `backend/models/parser_output.py`  
**Scope:** Add a structured evidence model for extracted risk-factor claims.

### T220
**File:** `backend/models/parser_output.py`  
**Scope:** Add evidence-bearing fields to the parser output contract for high-value extracted facts.

## Phase 3: Parser Extraction

### T221
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Extract `total_shares_offered` from the cover page or offering section using section-aware logic.

### T222
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Extract `public_float` using section-aware offering-structure logic.

### T223
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Extract `insider_selling_percentage` using selling-stockholder context instead of nearby-number regex.

### T224
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Extract `lockup_period_days` using section-aware underwriting/lock-up logic.

### T225
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Extract `revenue` from financial-statement context with evidence.

### T226
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Extract `revenue_growth_yoy` from financial-statement context with evidence.

### T227
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Extract raw burn-related signals from cash-flow context with evidence.

### T228
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Compute `burn_rate_monthly` from raw annual or period cash-use values instead of nearby-number regex guesses.

### T229
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Compute `cash_runway_months` from defensible balance-sheet and burn inputs where possible.

### T230
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Extract `use_of_proceeds` from the proper section with evidence.

### T231
**File:** `backend/agents/prospectus_parser.py`  
**Scope:** Replace risk-factor output with structured citation-grade risk items.

### T232
**File:** `tests/agents/test_prospectus_parser.py`  
**Scope:** Add realistic SEC-style fixture coverage for offering-structure extraction.

### T233
**File:** `tests/agents/test_prospectus_parser.py`  
**Scope:** Add realistic SEC-style fixture coverage for financial extraction.

### T234
**File:** `tests/agents/test_prospectus_parser.py`  
**Scope:** Add realistic SEC-style fixture coverage for use-of-proceeds extraction.

### T235
**File:** `tests/agents/test_prospectus_parser.py`  
**Scope:** Add realistic SEC-style fixture coverage for structured risk-factor extraction and TOC-noise rejection.

## Phase 4: Decision Contract Foundations

### T236
**File:** `backend/models/recommendation_output.py`  
**Scope:** Add a primary decision enum field: `buy | watch | avoid`.

### T237
**File:** `backend/models/recommendation_output.py`  
**Scope:** Add a decision-scope field: `pre_ipo_fund | post_ipo_direct | no_trade`.

### T238
**File:** `backend/models/recommendation_output.py`  
**Scope:** Add a structured `primary_vehicle` model.

### T239
**File:** `backend/models/recommendation_output.py`  
**Scope:** Add a structured `vehicle_candidates` model and field.

### T240
**File:** `backend/models/recommendation_output.py`  
**Scope:** Add `entry_triggers`, `watch_triggers`, and `kill_criteria` fields.

### T241
**File:** `backend/models/recommendation_output.py`  
**Scope:** Add `sizing_guidance`, `decision_rationale`, and `decision_evidence` fields.

### T242
**File:** `backend/agents/recommendation_engine.py`  
**Scope:** Add a helper that decides whether the analysis must degrade to `watch` based on parser confidence and missing evidence.

### T243
**File:** `backend/agents/recommendation_engine.py`  
**Scope:** Add a helper that distinguishes private backers from potentially public vehicles.

### T244
**File:** `backend/agents/recommendation_engine.py`  
**Scope:** Add a helper that validates minimum tradability evidence before a vehicle can be recommended.

## Phase 5: Decision Generation

### T245
**File:** `backend/agents/recommendation_engine.py`  
**Scope:** Build deterministic top-level `decision` output from evidence quality and scenario context.

### T246
**File:** `backend/agents/recommendation_engine.py`  
**Scope:** Build deterministic `decision_scope` output.

### T247
**File:** `backend/agents/recommendation_engine.py`  
**Scope:** Populate `primary_vehicle` only when tradability evidence passes validation.

### T248
**File:** `backend/agents/recommendation_engine.py`  
**Scope:** Populate `vehicle_candidates` while keeping private backers out of buyable-vehicle output.

### T249
**File:** `backend/agents/recommendation_engine.py`  
**Scope:** Generate explicit `entry_triggers` from upstream facts and scenario signals.

### T250
**File:** `backend/agents/recommendation_engine.py`  
**Scope:** Generate explicit `watch_triggers` from missing evidence and follow-up signals.

### T251
**File:** `backend/agents/recommendation_engine.py`  
**Scope:** Generate explicit `kill_criteria` from downside conditions and evidence weakness.

### T252
**File:** `backend/agents/recommendation_engine.py`  
**Scope:** Populate `decision_evidence` from parser and harvester evidence rather than loose text snippets.

### T253
**File:** `backend/agents/recommendation_engine.py`  
**Scope:** Rewrite narrative summary generation so it explains the structured decision rather than replacing it.

### T254
**File:** `tests/agents/test_recommendation_engine.py`  
**Scope:** Add tests for low-confidence downgrade to `watch`.

### T255
**File:** `tests/agents/test_recommendation_engine.py`  
**Scope:** Add tests proving a private VC/backer cannot become a buyable vehicle.

### T256
**File:** `tests/agents/test_recommendation_engine.py`  
**Scope:** Add tests proving no-tradable-vehicle cases cannot emit `buy pre_ipo_fund`.

### T257
**File:** `tests/agents/test_recommendation_engine.py`  
**Scope:** Add tests proving triggers and kill criteria are present when required.

## Phase 6: Judge Gates

### T258
**File:** `backend/agents/judge_agent.py`  
**Scope:** Add validation for a valid primary decision enum.

### T259
**File:** `backend/agents/judge_agent.py`  
**Scope:** Add validation that low-confidence parser output cannot pass with a `buy` decision.

### T260
**File:** `backend/agents/judge_agent.py`  
**Scope:** Add validation that `buy pre_ipo_fund` requires a verified tradable vehicle.

### T261
**File:** `backend/agents/judge_agent.py`  
**Scope:** Add validation that required triggers are present.

### T262
**File:** `backend/agents/judge_agent.py`  
**Scope:** Add validation that kill criteria are present.

### T263
**File:** `backend/agents/judge_agent.py`  
**Scope:** Add validation that decision rationale is traceable to evidence.

### T264
**File:** `tests/agents/test_judge_agent.py`  
**Scope:** Add tests for invalid decision enum rejection.

### T265
**File:** `tests/agents/test_judge_agent.py`  
**Scope:** Add tests for low-confidence `buy` rejection.

### T266
**File:** `tests/agents/test_judge_agent.py`  
**Scope:** Add tests for missing tradable vehicle rejection.

### T267
**File:** `tests/agents/test_judge_agent.py`  
**Scope:** Add tests for missing triggers and kill-criteria rejection.

## Phase 7: Frontend Contract

### T268
**File:** `frontend/src/api/client.ts`  
**Scope:** Add frontend types for the new structured decision contract.

### T269
**File:** `frontend/src/api/client.ts`  
**Scope:** Remove or downgrade prose-only fields as the primary recommendation dependency in the frontend contract.

## Phase 8: Presentation

### T270
**File:** `frontend/src/components/RecommendationSummaryPanel.tsx`  
**Scope:** Replace prose-first summary presentation with a decision card showing decision, vehicle, why now, entry triggers, and kill criteria.

### T271
**File:** `frontend/src/components/EvidencePanel.tsx`  
**Scope:** Replace generic support facts emphasis with decision-evidence emphasis.

### T272
**File:** `backend/export/pdf_summary.py`  
**Scope:** Render the structured decision contract in the summary PDF.

### T273
**File:** `backend/export/pdf_full_report.py`  
**Scope:** Render the structured decision contract in the full report PDF.

### T274
**File:** `tests/export/test_pdf_generation.py`  
**Scope:** Add export tests proving the decision contract is rendered in PDFs.

### T275
**File:** `tests/integration/test_analysis_end_to_end.py`  
**Scope:** Add an end-to-end test proving final output shape matches the structured decision contract.

## Recommended Execution Order
1. `T201`
2. `T202`
3. `T203`
4. `T204`
5. `T205`
6. `T206`
7. `T207`
8. `T208`
9. `T209`
10. `T210`
11. `T211`
12. `T212`
13. `T213`
14. `T214`
15. `T215`
16. `T216`
17. `T217`
18. `T218`
19. `T219`
20. `T220`
21. `T221`
22. `T222`
23. `T223`
24. `T224`
25. `T225`
26. `T226`
27. `T227`
28. `T228`
29. `T229`
30. `T230`
31. `T231`
32. `T232`
33. `T233`
34. `T234`
35. `T235`
36. `T236`
37. `T237`
38. `T238`
39. `T239`
40. `T240`
41. `T241`
42. `T242`
43. `T243`
44. `T244`
45. `T245`
46. `T246`
47. `T247`
48. `T248`
49. `T249`
50. `T250`
51. `T251`
52. `T252`
53. `T253`
54. `T254`
55. `T255`
56. `T256`
57. `T257`
58. `T258`
59. `T259`
60. `T260`
61. `T261`
62. `T262`
63. `T263`
64. `T264`
65. `T265`
66. `T266`
67. `T267`
68. `T268`
69. `T269`
70. `T270`
71. `T271`
72. `T272`
73. `T273`
74. `T274`
75. `T275`

## Success Bar
- The system can truthfully output:
  - `Buy [vehicle] because X, watch Y, exit if Z`
  - `Watch only; missing A/B/C before entry`
  - `Avoid; thesis breaks because X and no investable vehicle exists`
- The system cannot output:
  - a buyable fund recommendation for a private vehicle
  - a confident buy on low-confidence evidence
  - polished recommendation prose without traceable evidence
