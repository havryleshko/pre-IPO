from __future__ import annotations

from backend.services.reference_output_contract import load_canonical_reference_dataset

HEURISTIC_COHORT: tuple[str, ...] = ("RKLB", "PL", "IONS", "COHR", "IOVA", "QBTS", "MP", "ISRG", "LHX")

ADDITIONAL_COHORT: tuple[str, ...] = (
    "LYC.ASX",
    "BARC.L",
    "BAC",
    "C",
    "RTX",
    "LMT",
    "MS",
    "HWM",
    "ASTS",
    "RYTM",
    "ACHR",
    "V",
    "WDC",
    "LRCX",
    "MA",
    "TSLA",
    "RGTI",
    "MU",
    "WCC",
    "PLTR",
    "INTC",
)

REFERENCE_EXACT_COHORT: tuple[str, ...] = (
    "ABNB",
    "COIN",
    "DASH",
    "HOOD",
    "LYFT",
    "PLTR",
    "SNAP",
    "TSLA",
    "UBER",
)

ROUND3_MANDATORY_GATE_COHORT: tuple[str, ...] = (
    "TER",
    "SYM",
    "LUNR",
    "KRMN",
    "RPRX",
    "NOC",
    "INOD",
    "JOBY",
    "AIP",
    "OPEN",
    "DNA",
    "BIO",
)


def validate_reference_exact_cohort() -> list[str]:
    canonical_tickers = {record.ticker for record in load_canonical_reference_dataset() if record.ticker}
    return [ticker for ticker in REFERENCE_EXACT_COHORT if ticker not in canonical_tickers]

