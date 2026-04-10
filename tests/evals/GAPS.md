# Eval Gaps

## Current limitations

- Pre-IPO news claim extraction is evaluated with a deterministic baseline in `tests/evals/predictor_baseline.py`, not with a production extraction module.
- Filing contradiction checks rely on provided filing excerpts; they do not fetch full filing sections.
- Derived valuation oracles are filing-signature based:
  - Reddit: `$34.00` and `$748,000,000` implies `~$6.4B`.
  - Arm 424B4: `$51.00`, `95,500,000` ADS, `Total $4,870,500,000` implies `~$54.5B` equity at pricing.
  - Snowflake 424B4: `$120.00`, `28,000,000` shares, `Total $3,360,000,000` implies `~$33B` equity at pricing.

## Coverage

- Round 1: Reddit (`reddit_round1.json`), eight cases.
- Round 2: Arm Holdings (`arm_round1.json`), five cases; Snowflake (`snowflake_round1.json`), five cases (all `no_contradiction` in this round).
- Merged suite: `merged_eval_dataset()` in `tests/evals/load_gold.py` (18 cases).
- Pipeline-backed scoring path: `tests/evals/run_pipeline_case.py` + `tests/evals/pipeline_prediction_mapper.py` + `tests/evals/test_pipeline_eval_metrics.py`.

## Remaining gaps

- No production news-claim extractor wired to the eval harness.
- Pipeline mapping can score only claim types represented in current `SingleAgentResult` / parser fields; many news-specific claims remain skipped and are reported through `EVAL_PIPELINE_SKIPS`.
- Forbes Snowflake case uses revenue-only filing excerpt so amended valuation prose stays consistent with `no_contradiction`; full amended-range scoring would need that excerpt in gold.
- Bloomberg Snowflake item omits headline post-open market-cap figures not grounded in the 424B4 excerpt.
- No multilingual or non-US forms beyond Arm F-1 treated as `filing_type` `other`.

## Next expansions

- Add dedicated production claim extraction output and swap the baseline predictor hook.
- Add full-filing context slices per case to reduce excerpt-selection bias.
- Add more contradiction-positive companies beyond Reddit and Arm.
- Add a first-class product discrepancy output (news claim vs filing fact) so pipeline contradiction scoring no longer depends on `delivery_evidence` heuristics.

