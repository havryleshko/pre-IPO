# Round 2 eval baseline

- Generated at: `2026-04-13T16:04:11.385908+00:00`
- Git SHA: `1fdbb20404a6216a496cb8eb889354f97c6dca3f`
- API base: `http://127.0.0.1:8000`

## Cohort: `heuristic_9`

- Inputs: `RKLB, PL, IONS, COHR, IOVA, QBTS, MP, ISRG, LHX`
- Completed analyses: `9/9`
- `reference_exact`: `0`
- `heuristic`: `9`
- mandatory_field_coverage: `1.0000`
- missing_field_distribution: `{}`
- pattern_distribution: `{'Pattern 11: IPO timing, macro regime, and post-IPO mean reversion': 4, 'Pattern 1: Hyped growth story, weak long-run performance': 1, 'Pattern 2: Steady compounders with conservative narratives': 3, 'Pattern 4: Profitless growth that eventually inflects': 1}`
- canonical_reference_metrics: `not_applicable`

| Input | Analysis ID | Status | Resolved ticker | Bucket | Mandatory | Missing fields | Pattern | Reference row |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `RKLB` | `a280e623-d0b6-47f1-ad77-ba9e0ef5eee1` | `completed` | `RKLB` | `heuristic` | `7/7` | `-` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `PL` | `49134bfb-f744-4db2-8632-be0c6c0f6767` | `completed` | `PL` | `heuristic` | `7/7` | `-` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `IONS` | `ca786262-351c-4a94-94c3-8b327dbb37ba` | `completed` | `IONS` | `heuristic` | `7/7` | `-` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `COHR` | `11d59597-3ca2-41e8-80de-ec1c190d1272` | `completed` | `COHR` | `heuristic` | `7/7` | `-` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `IOVA` | `17a9a124-d511-4a47-9764-4666dd7c5523` | `completed` | `IOVA` | `heuristic` | `7/7` | `-` | `Pattern 1: Hyped growth story, weak long-run performance` | `-` |
| `QBTS` | `874d4492-e9f4-4727-a65c-b95eb3ae7fc4` | `completed` | `QBTS` | `heuristic` | `7/7` | `-` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `MP` | `ce935dd2-dd47-4500-98c6-bb30f2e02fce` | `completed` | `MP` | `heuristic` | `7/7` | `-` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `ISRG` | `9994b0ee-2b44-4cac-9836-47d8ebeeb360` | `completed` | `ISRG` | `heuristic` | `7/7` | `-` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `LHX` | `cf2319b3-dd2e-4f9f-968f-a6188f463320` | `completed` | `LHX` | `heuristic` | `7/7` | `-` | `Pattern 2: Steady compounders with conservative narratives` | `-` |

## Cohort: `reference_exact_9`

- Inputs: `ABNB, COIN, DASH, HOOD, LYFT, PLTR, SNAP, TSLA, UBER`
- Completed analyses: `9/9`
- `reference_exact`: `9`
- `heuristic`: `0`
- mandatory_field_coverage: `1.0000`
- missing_field_distribution: `{}`
- pattern_distribution: `{'Pattern 10: Lock-up expiries, insider selling, and narrative shifts (heavy early insider sales + disappointing filings).': 1, 'Pattern 11: IPO timing, macro regime, and post-IPO mean reversion (2021 hot-market peak followed by rate hikes).': 1, 'Pattern 11: IPO timing, macro regime, and post-IPO mean reversion (late-2020 issuance + macro tailwinds).': 1, 'Pattern 11: IPO timing, macro regime, and post-IPO mean reversion (pandemic-hot issuance).': 1, 'Pattern 4: Profitless growth that eventually inflects (long investment phase narrative).': 1, 'Pattern 4: Profitless growth that eventually inflects dramatically (long investment phase).': 1, 'Pattern 5: Hot-issue cohorts with broad underperformance (2019 tech-ride-hailing wave).': 1, 'Pattern 5: Hot-issue cohorts with broad underperformance (same 2019 cohort).': 1, 'Pattern 7: Forward-looking customer metrics as credible signals (granular cohort/LTV disclosure correlated with later unit economics).': 1}`
- canonical_reference_metrics:
  - mandatory_field_coverage: `1.0000`
  - pattern_accuracy: `1.0000`
  - failing_company_ids: `-`

| Input | Analysis ID | Status | Resolved ticker | Bucket | Mandatory | Missing fields | Pattern | Reference row |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ABNB` | `3e92059c-8d30-49b1-a830-7be417cdacb7` | `completed` | `ABNB` | `reference_exact` | `7/7` | `-` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion (late-2020 issuance + macro tailwinds).` | `Airbnb (ABNB)` |
| `COIN` | `04b831fb-40c2-46f7-8ebc-a691d6cbe0fa` | `completed` | `COIN` | `reference_exact` | `7/7` | `-` | `Pattern 7: Forward-looking customer metrics as credible signals (granular cohort/LTV disclosure correlated with later unit economics).` | `Coinbase (COIN)` |
| `DASH` | `4b0881aa-57fb-40bf-be70-753071f9ff8b` | `completed` | `DASH` | `reference_exact` | `7/7` | `-` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion (pandemic-hot issuance).` | `DoorDash (DASH)` |
| `HOOD` | `50fb4cec-45d1-4ced-a770-90ae3d09e8bb` | `completed` | `HOOD` | `reference_exact` | `7/7` | `-` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion (2021 hot-market peak followed by rate hikes).` | `Robinhood (HOOD)` |
| `LYFT` | `e4c7a9e8-555b-474a-9818-7511ab19f8f4` | `completed` | `LYFT` | `reference_exact` | `7/7` | `-` | `Pattern 5: Hot-issue cohorts with broad underperformance (2019 tech-ride-hailing wave).` | `Lyft (LYFT)` |
| `PLTR` | `07efa196-7c54-4b92-8768-2f421a297167` | `completed` | `PLTR` | `reference_exact` | `7/7` | `-` | `Pattern 4: Profitless growth that eventually inflects (long investment phase narrative).` | `Palantir (PLTR)` |
| `SNAP` | `2b444b26-39e3-4b47-ae81-af2dec4aa916` | `completed` | `SNAP` | `reference_exact` | `7/7` | `-` | `Pattern 10: Lock-up expiries, insider selling, and narrative shifts (heavy early insider sales + disappointing filings).` | `Snap (SNAP)` |
| `TSLA` | `3456d223-7aea-415d-9a57-f1a4bce3fcc2` | `completed` | `TSLA` | `reference_exact` | `7/7` | `-` | `Pattern 4: Profitless growth that eventually inflects dramatically (long investment phase).` | `Tesla (TSLA)` |
| `UBER` | `c22aeeb6-4fcd-4796-ac8f-b495381004fa` | `completed` | `UBER` | `reference_exact` | `7/7` | `-` | `Pattern 5: Hot-issue cohorts with broad underperformance (same 2019 cohort).` | `Uber (UBER)` |

## Cohort: `additional_21`

- Inputs: `LYC.ASX, BARC.L, BAC, C, RTX, LMT, MS, HWM, ASTS, RYTM, ACHR, V, WDC, LRCX, MA, TSLA, RGTI, MU, WCC, PLTR, INTC`
- Completed analyses: `20/21`
- `reference_exact`: `2`
- `heuristic`: `18`
- mandatory_field_coverage: `0.9184`
- missing_field_distribution: `{'company_ticker': 1, 'forecast_error': 1, 'industry_region': 1, 'ipo_date': 6, 'key_pre_ipo_claims': 1, 'long_term_outcome': 1, 'predicted_pattern': 1}`
- pattern_distribution: `{'Pattern 11: IPO timing, macro regime, and post-IPO mean reversion': 2, 'Pattern 2: Steady compounders with conservative narratives': 9, 'Pattern 4: Profitless growth that eventually inflects': 7, 'Pattern 4: Profitless growth that eventually inflects (long investment phase narrative).': 1, 'Pattern 4: Profitless growth that eventually inflects dramatically (long investment phase).': 1}`
- canonical_reference_metrics:
  - mandatory_field_coverage: `1.0000`
  - pattern_accuracy: `1.0000`
  - failing_company_ids: `-`

| Input | Analysis ID | Status | Resolved ticker | Bucket | Mandatory | Missing fields | Pattern | Reference row |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `LYC.ASX` | `1dcdcfc8-ef6d-40ab-a5f9-3c0e81934c13` | `failed` | `-` | `unavailable` | `0/7` | `company_ticker, industry_region, ipo_date, key_pre_ipo_claims, long_term_outcome, forecast_error, predicted_pattern` | `-` | `-` |
| `BARC.L` | `ce37500d-c744-4a8b-bedb-517cb7dad7f7` | `completed` | `BTI` | `heuristic` | `7/7` | `-` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `BAC` | `f358c790-8139-4f3c-85bf-bbc169245ad6` | `completed` | `BAC` | `heuristic` | `6/7` | `ipo_date` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `C` | `a654da99-6725-4812-b8c0-4349c17299fa` | `completed` | `C` | `heuristic` | `6/7` | `ipo_date` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `RTX` | `4f7193ff-ae94-4c6f-815e-dbc8c40258ec` | `completed` | `RTX` | `heuristic` | `6/7` | `ipo_date` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `LMT` | `b6cf3bc0-2935-4abc-8214-0e81d28de2b2` | `completed` | `LMT` | `heuristic` | `6/7` | `ipo_date` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `MS` | `1c4ed6b5-a3da-4579-86c7-41faa6aa7c49` | `completed` | `MS` | `heuristic` | `7/7` | `-` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `HWM` | `3ebacb2e-b5d2-4764-8ef0-4c2d207847df` | `completed` | `HWM` | `heuristic` | `7/7` | `-` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `ASTS` | `ad5cebde-db5f-403e-9d0d-e687b894c9f0` | `completed` | `ASTS` | `heuristic` | `7/7` | `-` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `RYTM` | `a1d43a3b-8f11-4c5c-8335-e26c915d2980` | `completed` | `RYTM` | `heuristic` | `7/7` | `-` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `ACHR` | `4e3bcdb2-923b-4d56-b6ba-e70b79d94a4b` | `completed` | `ACHR` | `heuristic` | `7/7` | `-` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `V` | `96242d6e-19e9-4e30-9b10-9af839ae17a3` | `completed` | `V` | `heuristic` | `7/7` | `-` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `WDC` | `c9567735-fb5b-4965-8732-6562d268b133` | `completed` | `WDC` | `heuristic` | `6/7` | `ipo_date` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `LRCX` | `f0d131ae-7e9d-47bc-9e67-479f5d0a617f` | `completed` | `LRCX` | `heuristic` | `7/7` | `-` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `MA` | `4451d25d-7517-4b04-b9f5-36fdc22a4707` | `completed` | `MA` | `heuristic` | `7/7` | `-` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `TSLA` | `2a04ec31-281c-4ff2-a30d-e470d8b0a22b` | `completed` | `TSLA` | `reference_exact` | `7/7` | `-` | `Pattern 4: Profitless growth that eventually inflects dramatically (long investment phase).` | `Tesla (TSLA)` |
| `RGTI` | `e5ce546f-4f85-488b-914a-bb47b131a8e4` | `completed` | `RGTI` | `heuristic` | `7/7` | `-` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `MU` | `49bd59c7-fb4d-41bc-ae62-89163bd74407` | `completed` | `MU` | `heuristic` | `7/7` | `-` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `WCC` | `6b339a12-5e2c-4884-8ff4-b168d8337bcd` | `completed` | `WCC` | `heuristic` | `7/7` | `-` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `PLTR` | `636155f2-c3a3-4c36-872d-f2382f08cdce` | `completed` | `PLTR` | `reference_exact` | `7/7` | `-` | `Pattern 4: Profitless growth that eventually inflects (long investment phase narrative).` | `Palantir (PLTR)` |
| `INTC` | `8ce1b75f-d2e1-4f70-abff-9f2ae80a835f` | `completed` | `INTC` | `heuristic` | `7/7` | `-` | `Pattern 4: Profitless growth that eventually inflects` | `-` |

