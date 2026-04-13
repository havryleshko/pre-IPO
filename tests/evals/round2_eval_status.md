# Round 2 eval + Rich UX status

## Scope

This note captures Round 2 outcomes across locked cohorts and the incremental Rich/Textual presentation pass.

- Cohort runner: `tests/evals/run_round2_baseline.py`
- Cohort definitions: `tests/evals/round2_cohorts.py`
- Baseline artifacts: `tests/evals/round2_baseline.md`, `tests/evals/round2_baseline.json`
- Round 1 comparison note: `tests/evals/round1_eval_status.md`

## Cohort results

### Heuristic cohort (`RKLB, PL, IONS, COHR, IOVA, QBTS, MP, ISRG, LHX`)

- Completed: `9/9`
- Split: `reference_exact=0`, `heuristic=9`
- Mandatory field coverage: `1.0000` (`63/63`)
- Projection completeness: `1.0000`
- Missing fields: none
- Canonical metrics: `not_applicable` (no canonical matches by design)

### Reference-exact cohort (`ABNB, COIN, DASH, HOOD, LYFT, PLTR, SNAP, TSLA, UBER`)

- Completed: `9/9`
- Split: `reference_exact=9`, `heuristic=0`
- Mandatory field coverage: `1.0000`
- Pattern accuracy: `1.0000`
- Projection field coverage: `1.0000`
- Decline-band hit rate: `0.3333`
- Rebound-signal accuracy: `0.4444`
- Failing IDs under canonical scoring: `ABNB, COIN, DASH, HOOD, LYFT, SNAP, UBER`

### Additional cohort (`LYC.ASX, BARC.L, BAC, C, RTX, LMT, MS, HWM, ASTS, RYTM, ACHR, V, WDC, LRCX, MA, TSLA, RGTI, MU, WCC, PLTR, INTC`)

- Completed: `20/21`
- Split: `reference_exact=2` (`TSLA`, `PLTR`), `heuristic=18`
- Mandatory field coverage: `0.9184`
- Projection completeness: `0.9524`
- Main missing field pressure: `ipo_date` (`6` misses)
- One hard failure: `LYC.ASX` (no structured output row generated)

## Round 1 -> Round 2 deltas

- The original 9-name heuristic cohort improved from `0.9524` mandatory coverage to `1.0000`.
- The `ipo_date` gap seen in Round 1 (`IONS`, `COHR`, `LHX`) is closed in this run.
- Round 2 now includes a true canonical cohort, so `ReferenceOutputMetrics` are no longer blocked by cohort design.
- The additional 21-name cohort confirms mixed behavior: mostly heuristic rows, with two canonical hits.

## Implemented changes in this round

### Eval/reporting

- Added fixed cohort definitions and canonical preflight validation in `tests/evals/round2_cohorts.py`.
- Added cohort-split runner/reporter in `tests/evals/run_round2_baseline.py`:
  - per-company classification (`reference_exact` vs `heuristic`)
  - canonical metrics where applicable
  - heuristic rubric metrics (mandatory/projection/analog/projection-basis/pattern distribution)
- Added runner verification tests in `tests/evals/test_round2_baseline_runner.py`.

### IPO-date reliability

- Relaxed IPO-date plausibility floor in `backend/tools/yfinance_client.py` from year `2000` to `1980`.
- Updated resolver tests in `tests/tools/test_yfinance_client.py` to reflect accepted historical IPO dates.

### Incremental Rich/Textual UX

- Enhanced `tui/render.py`:
  - top summary panel (pattern id, source, mandatory completeness, delivery direction)
  - color semantics for outcome percentages and claim-check status
  - added patterns/news sections in CLI Rich output
  - aligned section ordering so claim checks appear before patterns in plain/markdown output
- Improved status panel styling in `tui/app.py` for running/completed/flags/failed states.
- Extended ordering checks in `tests/tui/test_render_export.py`.

## Validation run

- `pytest tests/evals/test_reference_output_contract.py tests/evals/test_reference_output_scoring.py tests/evals/test_round2_baseline_runner.py tests/tui/test_render_export.py tests/cli/test_preipo_cli.py tests/tools/test_yfinance_client.py -q`
- Result: `42 passed`

## Top 3 improvement candidates (next round)

1. Investigate `LYC.ASX` failure path and decide whether symbol normalization for exchange suffixes should be added.
2. Continue expanding canonical pattern coverage without changing canonical labels.
3. Add one compact “cohort delta” appendix to automate before/after comparison in future runs.