# Eval Gaps

## Current limitations

- The harness still injects **filing excerpts**, not full EDGAR documents; parser and discrepancy logic only see what gold includes.
- **Implied equity** when the excerpt has no explicit billion valuation sentence still uses **legacy filing signatures** in `news_filing_discrepancy._infer_filing_valuation_billions` (Reddit 424B4 ~$6.4B, Arm ~$54.5B, Snowflake 424B4 ~$33B). Prefer adding **range or midpoint language** to gold excerpts so generic rules apply first.
- **Generic filing helpers** (recent): billion-band midpoint (`between $A billion and $B billion`, `$X billion to $Y billion`), keyword-scoped single-billion phrases, and **Total $N** gross proceeds before falling back to scanning dollar amounts.

## Coverage

- Round 1: Reddit (`reddit_round1.json`), eight cases.
- Round 2: Arm Holdings (`arm_round1.json`), five cases; Snowflake (`snowflake_round1.json`), five cases (all `no_contradiction` in that round).
- Round 3: Instacart (`instacart_round1.json`), two cases (one `contradiction` on gross proceeds vs raise rumor, one `no_contradiction` revenue).
- Merged suite: `merged_eval_dataset()` in `tests/evals/load_gold.py` (twenty cases).
- Pipeline-backed scoring path: `tests/evals/run_pipeline_case.py` + `tests/evals/pipeline_prediction_mapper.py` + `tests/evals/test_pipeline_eval_metrics.py`.

## Product alignment (recent)

- The single-agent pipeline persists optional `news_derived_claims` and `news_filing_discrepancies` on `SingleAgentResult` (see `backend/services/news_claim_extractor.py`, `backend/services/news_filing_discrepancy.py`, wired in `SingleAgentToolCaller`).
- The pipeline eval mapper prefers those fields when present; `delivery_evidence` is used for contradiction mapping only when `news_filing_discrepancies` is empty.
- **Valuation “up to”** phrasing in news evidence uses **approximate** comparison for discrepancy checks to avoid false positives against higher filing-implied values.

## Remaining gaps

- **Snowflake–Bloomberg (2020-09-15):** gold `claims_to_extract` stay limited to price and share count grounded in the 424B4 snippet; headline post-open market-cap figures are out of scope unless the article and excerpt are extended together.
- **Other rows:** repeat the Forbes pattern (longer `filing_excerpt` or narrower `pre_ipo_news_excerpt`) wherever the article cites numbers not present in the filing text.
- **No multilingual or non-US** forms beyond Arm F-1 treated as `filing_type` `other`.

## Next expansions

- Add fuller filing slices for remaining cases (especially any still “thin” on pricing/proceeds).
- Further reduce legacy valuation signatures by encoding implied equity as explicit sentences in gold where factually correct.
- Optional API exposure of `news_derived_claims` / `news_filing_discrepancies` for non-TUI clients if needed.