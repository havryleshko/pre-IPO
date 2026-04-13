# Round 2 eval baseline

- Generated at: `2026-04-13T10:16:30.634843+00:00`
- Git SHA: `a4db8ac8d2906afa8d1c1a87968a16145b81ede6`
- API base: `http://127.0.0.1:8000`

## Cohort: `heuristic_9`

- Inputs: `RKLB, PL, IONS, COHR, IOVA, QBTS, MP, ISRG, LHX`
- Completed analyses: `9/9`
- `reference_exact`: `0`
- `heuristic`: `9`
- mandatory_field_coverage: `1.0000`
- projection_completeness: `1.0000`
- analog_companies_presence: `1.0000`
- projection_basis_presence: `1.0000`
- missing_field_distribution: `{}`
- pattern_distribution: `{'Pattern 11: IPO timing, macro regime, and post-IPO mean reversion': 4, 'Pattern 1: Hyped growth story, weak long-run performance': 1, 'Pattern 2: Steady compounders with conservative narratives': 3, 'Pattern 4: Profitless growth that eventually inflects': 1}`
- canonical_reference_metrics: `not_applicable`

| Input | Analysis ID | Status | Resolved ticker | Bucket | Mandatory | Missing fields | Projection complete | Pattern | Reference row |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `RKLB` | `0d90c15d-930d-4372-9f23-52e0ad3859f2` | `completed` | `RKLB` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `PL` | `4857c967-7aed-459b-92d4-bb7d954a4bfe` | `completed` | `PL` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `IONS` | `fd7396e9-04e8-4801-8b75-a34f0ba23251` | `completed` | `IONS` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `COHR` | `cd563432-a8eb-4ecf-9aef-5f40f33dc1e4` | `completed` | `COHR` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `IOVA` | `897abe21-c44f-42a0-a555-1811782a0590` | `completed` | `IOVA` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 1: Hyped growth story, weak long-run performance` | `-` |
| `QBTS` | `8fde8033-6475-4454-9736-0dc9c337fdcf` | `completed` | `QBTS` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `MP` | `d65c3ab5-6598-4a59-9c40-be3a20d79cb9` | `completed` | `MP` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `ISRG` | `213c0018-bc8b-45eb-9e17-3b8c9d9eaa72` | `completed` | `ISRG` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `LHX` | `00761c43-7ed8-4478-8e79-0ef0d15cf0b2` | `completed` | `LHX` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 2: Steady compounders with conservative narratives` | `-` |

## Cohort: `reference_exact_9`

- Inputs: `ABNB, COIN, DASH, HOOD, LYFT, PLTR, SNAP, TSLA, UBER`
- Completed analyses: `9/9`
- `reference_exact`: `9`
- `heuristic`: `0`
- mandatory_field_coverage: `1.0000`
- projection_completeness: `1.0000`
- analog_companies_presence: `1.0000`
- projection_basis_presence: `1.0000`
- missing_field_distribution: `{}`
- pattern_distribution: `{'Pattern 10: Lock-up expiries, insider selling, and narrative shifts (heavy early insider sales + disappointing filings).': 1, 'Pattern 11: IPO timing, macro regime, and post-IPO mean reversion (2021 hot-market peak followed by rate hikes).': 1, 'Pattern 11: IPO timing, macro regime, and post-IPO mean reversion (late-2020 issuance + macro tailwinds).': 1, 'Pattern 11: IPO timing, macro regime, and post-IPO mean reversion (pandemic-hot issuance).': 1, 'Pattern 4: Profitless growth that eventually inflects (long investment phase narrative).': 1, 'Pattern 4: Profitless growth that eventually inflects dramatically (long investment phase).': 1, 'Pattern 5: Hot-issue cohorts with broad underperformance (2019 tech-ride-hailing wave).': 1, 'Pattern 5: Hot-issue cohorts with broad underperformance (same 2019 cohort).': 1, 'Pattern 7: Forward-looking customer metrics as credible signals (granular cohort/LTV disclosure correlated with later unit economics).': 1}`
- canonical_reference_metrics:
  - mandatory_field_coverage: `1.0000`
  - pattern_accuracy: `1.0000`
  - projection_field_coverage: `1.0000`
  - decline_band_hit_rate: `0.3333`
  - rebound_signal_accuracy: `0.4444`
  - failing_company_ids: `ABNB, COIN, DASH, HOOD, LYFT, SNAP, UBER`

| Input | Analysis ID | Status | Resolved ticker | Bucket | Mandatory | Missing fields | Projection complete | Pattern | Reference row |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ABNB` | `4bd4076b-a5f4-46f8-95bc-2c39e19bf799` | `completed` | `ABNB` | `reference_exact` | `7/7` | `-` | `yes` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion (late-2020 issuance + macro tailwinds).` | `Airbnb (ABNB)` |
| `COIN` | `6537eded-27e4-40e8-a6cb-e5731f0eeff5` | `completed` | `COIN` | `reference_exact` | `7/7` | `-` | `yes` | `Pattern 7: Forward-looking customer metrics as credible signals (granular cohort/LTV disclosure correlated with later unit economics).` | `Coinbase (COIN)` |
| `DASH` | `ca31939c-013c-4b0d-9f77-5e162ef51067` | `completed` | `DASH` | `reference_exact` | `7/7` | `-` | `yes` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion (pandemic-hot issuance).` | `DoorDash (DASH)` |
| `HOOD` | `4f3ffbe9-9fb2-4ae3-8175-f9cd0841e103` | `completed` | `HOOD` | `reference_exact` | `7/7` | `-` | `yes` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion (2021 hot-market peak followed by rate hikes).` | `Robinhood (HOOD)` |
| `LYFT` | `917baf69-ee7a-4328-89e6-d9370b5224ec` | `completed` | `LYFT` | `reference_exact` | `7/7` | `-` | `yes` | `Pattern 5: Hot-issue cohorts with broad underperformance (2019 tech-ride-hailing wave).` | `Lyft (LYFT)` |
| `PLTR` | `a459ac60-37a7-4c3c-b2c8-8809340c95ec` | `completed` | `PLTR` | `reference_exact` | `7/7` | `-` | `yes` | `Pattern 4: Profitless growth that eventually inflects (long investment phase narrative).` | `Palantir (PLTR)` |
| `SNAP` | `eb6b8f0d-e76a-422a-b015-1f1b4456ad66` | `completed` | `SNAP` | `reference_exact` | `7/7` | `-` | `yes` | `Pattern 10: Lock-up expiries, insider selling, and narrative shifts (heavy early insider sales + disappointing filings).` | `Snap (SNAP)` |
| `TSLA` | `4a44e133-cb24-4b69-8714-6891ea013b43` | `completed` | `TSLA` | `reference_exact` | `7/7` | `-` | `yes` | `Pattern 4: Profitless growth that eventually inflects dramatically (long investment phase).` | `Tesla (TSLA)` |
| `UBER` | `c1b94723-fdad-45a6-8672-5c9ebc185e14` | `completed` | `UBER` | `reference_exact` | `7/7` | `-` | `yes` | `Pattern 5: Hot-issue cohorts with broad underperformance (same 2019 cohort).` | `Uber (UBER)` |

## Cohort: `additional_21`

- Inputs: `LYC.ASX, BARC.L, BAC, C, RTX, LMT, MS, HWM, ASTS, RYTM, ACHR, V, WDC, LRCX, MA, TSLA, RGTI, MU, WCC, PLTR, INTC`
- Completed analyses: `20/21`
- `reference_exact`: `2`
- `heuristic`: `18`
- mandatory_field_coverage: `0.9184`
- projection_completeness: `0.9524`
- analog_companies_presence: `0.9524`
- projection_basis_presence: `0.9524`
- missing_field_distribution: `{'company_ticker': 1, 'forecast_error': 1, 'industry_region': 1, 'ipo_date': 6, 'key_pre_ipo_claims': 1, 'long_term_outcome': 1, 'predicted_pattern': 1}`
- pattern_distribution: `{'Pattern 11: IPO timing, macro regime, and post-IPO mean reversion': 2, 'Pattern 2: Steady compounders with conservative narratives': 9, 'Pattern 4: Profitless growth that eventually inflects': 7, 'Pattern 4: Profitless growth that eventually inflects (long investment phase narrative).': 1, 'Pattern 4: Profitless growth that eventually inflects dramatically (long investment phase).': 1}`
- canonical_reference_metrics:
  - mandatory_field_coverage: `1.0000`
  - pattern_accuracy: `1.0000`
  - projection_field_coverage: `1.0000`
  - decline_band_hit_rate: `1.0000`
  - rebound_signal_accuracy: `1.0000`
  - failing_company_ids: `-`

| Input | Analysis ID | Status | Resolved ticker | Bucket | Mandatory | Missing fields | Projection complete | Pattern | Reference row |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `LYC.ASX` | `14c0b9a3-c886-4b0d-bd67-519a1b1729b4` | `failed` | `-` | `unavailable` | `0/7` | `company_ticker, industry_region, ipo_date, key_pre_ipo_claims, long_term_outcome, forecast_error, predicted_pattern` | `no` | `-` | `-` |
| `BARC.L` | `7e570947-a1d1-41a7-89a9-2628be24e258` | `completed` | `BTI` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `BAC` | `77875d95-42f0-463c-928b-6b8c500e13b3` | `completed` | `BAC` | `heuristic` | `6/7` | `ipo_date` | `yes` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `C` | `38fcb0f7-dd7b-4388-b30c-239e3c121f0d` | `completed` | `C` | `heuristic` | `6/7` | `ipo_date` | `yes` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `RTX` | `43fa9ba4-c2c3-4052-8e70-e0bb4ba531be` | `completed` | `RTX` | `heuristic` | `6/7` | `ipo_date` | `yes` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `LMT` | `f765472c-3561-4049-a72e-a4173932b74f` | `completed` | `LMT` | `heuristic` | `6/7` | `ipo_date` | `yes` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `MS` | `2129d2db-cb11-4448-b6f9-d06552407373` | `completed` | `MS` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `HWM` | `0d8ac3ca-7b4d-4ffb-b76f-80efa9fff4e9` | `completed` | `HWM` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `ASTS` | `6780e07e-c999-47cb-a7f9-f5f7b72b1e86` | `completed` | `ASTS` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `RYTM` | `bfa2e82b-614b-4943-9133-54cce932c847` | `completed` | `RYTM` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `ACHR` | `f8b137c7-a195-41d0-b296-2c7e083d0e3d` | `completed` | `ACHR` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `V` | `83aa7702-0f58-4515-9df8-bf4616f3889c` | `completed` | `V` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `WDC` | `f0393286-d183-4a57-8ddb-69cae2c3a349` | `completed` | `WDC` | `heuristic` | `6/7` | `ipo_date` | `yes` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `LRCX` | `0cd5511a-d493-4e6b-ae17-1dced318daa7` | `completed` | `LRCX` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `MA` | `32bf480e-a56d-4784-a06d-11ce044a6486` | `completed` | `MA` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `TSLA` | `d5be908b-a3dd-4822-8667-18cb2a265348` | `completed` | `TSLA` | `reference_exact` | `7/7` | `-` | `yes` | `Pattern 4: Profitless growth that eventually inflects dramatically (long investment phase).` | `Tesla (TSLA)` |
| `RGTI` | `43210ed3-3b05-4cf2-a4c5-313a08d9a699` | `completed` | `RGTI` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `MU` | `539a6e90-a6c7-40ad-a28b-c05db556de25` | `completed` | `MU` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `WCC` | `c29130e7-f4dc-4aa1-ba70-39eeef67b431` | `completed` | `WCC` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `PLTR` | `b8025e75-fa4c-4cfa-91f3-377e3b1c3511` | `completed` | `PLTR` | `reference_exact` | `7/7` | `-` | `yes` | `Pattern 4: Profitless growth that eventually inflects (long investment phase narrative).` | `Palantir (PLTR)` |
| `INTC` | `701fe54f-8160-4ef7-ab1e-89b10229790a` | `completed` | `INTC` | `heuristic` | `7/7` | `-` | `yes` | `Pattern 4: Profitless growth that eventually inflects` | `-` |

