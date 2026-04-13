# Round 1 eval status

## Scope

This note summarizes the current Round 1 baseline for the new output-contract eval flow.

- Reference inputs: `tests/evals/data/table-2.csv`, `tests/evals/data/table-3.csv`, `tests/evals/data/table-4.csv`
- Pattern reference: `tests/evals/data/Patterns in Pre-IPO Narratives vs Post-IPO Realities (2006–2025).md`
- Fixed company run order: `RKLB`, `PL`, `IONS`, `COHR`, `IOVA`, `QBTS`, `MP`, `ISRG`, `LHX`
- Baseline artifacts: `tests/evals/round1_reference_baseline.md`, `tests/evals/round1_reference_baseline.json`
- Git SHA for this run: `a4db8ac8d2906afa8d1c1a87968a16145b81ede6`

## Where We Stand

- All 9/9 analyses completed successfully.
- 0/9 inputs landed on `reference_exact`.
- 9/9 inputs landed on `heuristic`.
- Canonical `ReferenceOutputMetrics` are `not_applicable` for this cohort because none of the inputs matched canonical CSV rows.
- Cohort-level mandatory-field fill rate was `60/63 = 95.24%`.
- The only missing mandatory field across the cohort was `ipo_date`, missing for `IONS`, `COHR`, and `LHX`.

## Per-company result


| Input  | Status      | Bucket      | Mandatory fields | Missing fields | Pattern      |
| ------ | ----------- | ----------- | ---------------- | -------------- | ------------ |
| `RKLB` | `completed` | `heuristic` | `7/7`            | `-`            | `Pattern 11` |
| `PL`   | `completed` | `heuristic` | `7/7`            | `-`            | `Pattern 11` |
| `IONS` | `completed` | `heuristic` | `6/7`            | `ipo_date`     | `Pattern 4`  |
| `COHR` | `completed` | `heuristic` | `6/7`            | `ipo_date`     | `Pattern 4`  |
| `IOVA` | `completed` | `heuristic` | `7/7`            | `-`            | `Pattern 1`  |
| `QBTS` | `completed` | `heuristic` | `7/7`            | `-`            | `Pattern 11` |
| `MP`   | `completed` | `heuristic` | `7/7`            | `-`            | `Pattern 11` |
| `ISRG` | `completed` | `heuristic` | `7/7`            | `-`            | `Pattern 2`  |
| `LHX`  | `completed` | `heuristic` | `6/7`            | `ipo_date`     | `Pattern 4`  |


## What This Baseline Actually Proves

- The current pipeline can produce the new output shape consistently for the chosen nine-company cohort.
- Yahoo-backed `industry_region` filling is working for non-reference names.
- Mandatory field coverage is strong for heuristic cases, but IPO-date completion is not reliable enough yet.
- This run does **not** measure canonical row-match accuracy, pattern accuracy against CSV gold, or projection calibration against canonical rows, because the chosen cohort never touches the `reference_exact` path.

## What It Does Not Prove Yet

- Whether ticker/name matching against the canonical CSV set is good enough in production.
- Whether canonical pattern labels are reproduced correctly when a company does exist in the reference dataset.
- Whether decline-band and rebound-probability scoring are correct against gold outcomes.
- Whether the heuristic pattern mapper is high quality; this run only shows what it emits, not whether those classifications are correct.

## Signals From The Run

- Heuristic classification is concentrated: `Pattern 11` appears 4 times and `Pattern 4` appears 3 times, with only one `Pattern 1` and one `Pattern 2`.
- Missing-field pressure is narrow: every miss was `ipo_date`, not a broader contract-shape failure.
- Because all nine names were outside the canonical CSV reference set, this cohort is effectively a **heuristic baseline cohort**, not a mixed reference-vs-heuristic cohort.

## Potential Improvements Based On This Eval

These are improvement candidates suggested by the baseline, not automatic fixes.

1. Add a small second cohort that is guaranteed to hit `reference_exact` if you want actual canonical scoring in Round 1. Without that, `ReferenceOutputMetrics` will keep being `not_applicable`.
2. Improve IPO-date resolution for heuristic names, since `ipo_date` was the only missing mandatory field and accounted for all coverage misses in this cohort.
3. Add a heuristic-only reporting layer so non-reference runs can be evaluated explicitly instead of only being described. Right now the scorer is built for canonical-row comparison, so heuristic cohorts mostly produce operational observations.
4. Add more audit detail for heuristic outputs, such as `analog_companies` and `projection_basis`, so pattern decisions are easier to review before changing heuristic logic.
5. Investigate whether the current heuristic mapper is too biased toward `Pattern 11` / `Pattern 4`, but do not retune from this cohort alone. One cohort is not enough evidence.

## Recommended Next Step

Keep this document as the current Round 1 status note, and for the next pass choose one of two clean directions:

- Add a **reference cohort** so canonical scoring becomes real.
- Keep this exact nine-company heuristic cohort and define a **heuristic eval rubric** instead of pretending canonical metrics apply.

