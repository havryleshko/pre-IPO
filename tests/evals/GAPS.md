# Eval Gaps

## Current limitations

- Filing contradiction checks still rely on excerpt text and heuristics (signatures for implied valuation / proceeds); they do not fetch full filing sections in the eval harness.
- Derived valuation oracles remain filing-signature based where the filing excerpt omits an explicit equity value:
  - Reddit 424B4: `$34.00` and `$748,000,000` implies `~$6.4B`.
  - Arm 424B4: `$51.00`, `95,500,000` ADS, `Total $4,870,500,000` implies `~$54.5B`.
  - Snowflake 424B4: `$120.00`, `28,000,000` shares, `Total $3,360,000,000` implies `~$33B`.

## Coverage

- Round 1: Reddit (`reddit_round1.json`), eight cases.
- Round 2: Arm Holdings (`arm_round1.json`), five cases; Snowflake (`snowflake_round1.json`), five cases (all `no_contradiction` in that round).
- Round 3: Instacart (`instacart_round1.json`), two cases (one `contradiction` on gross proceeds vs raise rumor, one `no_contradiction` revenue).
- Merged suite: `merged_eval_dataset()` in `tests/evals/load_gold.py` (twenty cases).
- Pipeline-backed scoring path: `tests/evals/run_pipeline_case.py` + `tests/evals/pipeline_prediction_mapper.py` + `tests/evals/test_pipeline_eval_metrics.py`.

## Product alignment (recent)

- The single-agent pipeline now persists optional `news_derived_claims` and `news_filing_discrepancies` on `SingleAgentResult` (see `backend/services/news_claim_extractor.py`, `backend/services/news_filing_discrepancy.py`, wired in `SingleAgentToolCaller`).
- The pipeline eval mapper prefers those fields when present; `delivery_evidence` is used for contradiction mapping only when `news_filing_discrepancies` is empty.

## Remaining gaps

- Forbes Snowflake case uses a revenue-only filing excerpt so amended valuation prose stays consistent with `no_contradiction`; full amended-range scoring would need that excerpt in gold.
- Bloomberg Snowflake item omits headline post-open market-cap figures not grounded in the 424B4 excerpt.
- No multilingual or non-US forms beyond Arm F-1 treated as `filing_type` `other`.

## Next expansions

- Add fuller filing context slices per case to reduce excerpt-selection bias.
- Broaden production extraction beyond regex v1 (e.g. additional claim types, safer floor vs ceiling detection from phrasing).
- Optional API exposure of `news_derived_claims` / `news_filing_discrepancies` for non-TUI clients if needed.
