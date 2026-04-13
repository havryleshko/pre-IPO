# Round 1 reference baseline

- Generated at: `2026-04-13T08:52:36.538742+00:00`
- Git SHA: `a4db8ac8d2906afa8d1c1a87968a16145b81ede6`
- API base: `http://127.0.0.1:8000`
- Inputs: `RKLB, PL, IONS, COHR, IOVA, QBTS, MP, ISRG, LHX`

## Per-company

| Input | Analysis ID | Status | Resolved ticker | Bucket | Row source | Industry/Region source | Mandatory fields | Missing fields | Pattern | Reference row |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `RKLB` | `d3b2393b-9dd7-4553-b7ca-d2e47f74b9aa` | `completed` | `RKLB` | `heuristic` | `heuristic` | `yahoo_info` | `7/7` | `-` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `PL` | `de18c449-f191-4c4a-b4eb-ae45c248a25e` | `completed` | `PL` | `heuristic` | `heuristic` | `yahoo_info` | `7/7` | `-` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `IONS` | `19ba3d17-81fc-451b-a4f0-1eb47c71966b` | `completed` | `IONS` | `heuristic` | `heuristic` | `yahoo_info` | `6/7` | `ipo_date` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `COHR` | `2c8aec6b-1ea4-46be-b8c3-b7513405297b` | `completed` | `COHR` | `heuristic` | `heuristic` | `yahoo_info` | `6/7` | `ipo_date` | `Pattern 4: Profitless growth that eventually inflects` | `-` |
| `IOVA` | `c00e1836-790f-4d02-abac-fdb6cf4993df` | `completed` | `IOVA` | `heuristic` | `heuristic` | `yahoo_info` | `7/7` | `-` | `Pattern 1: Hyped growth story, weak long-run performance` | `-` |
| `QBTS` | `e6c9a0dd-9acd-4dd2-88ff-59dad1ff36b6` | `completed` | `QBTS` | `heuristic` | `heuristic` | `yahoo_info` | `7/7` | `-` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `MP` | `728de4cb-94aa-4646-ad1e-4f99f6ebe21e` | `completed` | `MP` | `heuristic` | `heuristic` | `yahoo_info` | `7/7` | `-` | `Pattern 11: IPO timing, macro regime, and post-IPO mean reversion` | `-` |
| `ISRG` | `d02b9fd3-d353-42fd-8ee2-bf803780fff3` | `completed` | `ISRG` | `heuristic` | `heuristic` | `yahoo_info` | `7/7` | `-` | `Pattern 2: Steady compounders with conservative narratives` | `-` |
| `LHX` | `69610f21-2ac3-4e68-9d9f-dc88626ed065` | `completed` | `LHX` | `heuristic` | `heuristic` | `yahoo_info` | `6/7` | `ipo_date` | `Pattern 4: Profitless growth that eventually inflects` | `-` |

## Aggregate

- Completed analyses: `9/9`
- `reference_exact`: `0`
- `heuristic`: `9`
- ReferenceOutputMetrics: `not_applicable` (no inputs matched canonical reference rows)
