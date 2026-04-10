from pathlib import Path

from backend.models.eval_case import EvalCase, EvalDataset


def _gold_dir() -> Path:
    return Path(__file__).resolve().parent / "gold"


def reddit_round1_path() -> Path:
    return _gold_dir() / "reddit_round1.json"


def arm_round1_path() -> Path:
    return _gold_dir() / "arm_round1.json"


def snowflake_round1_path() -> Path:
    return _gold_dir() / "snowflake_round1.json"


def load_eval_dataset(path: Path) -> EvalDataset:
    return EvalDataset.model_validate_json(path.read_text(encoding="utf-8"))


def load_reddit_round1() -> EvalDataset:
    return load_eval_dataset(reddit_round1_path())


def load_arm_round1() -> EvalDataset:
    return load_eval_dataset(arm_round1_path())


def load_snowflake_round1() -> EvalDataset:
    return load_eval_dataset(snowflake_round1_path())


def load_all_eval_datasets() -> list[EvalDataset]:
    return [
        load_reddit_round1(),
        load_arm_round1(),
        load_snowflake_round1(),
    ]


def merged_eval_cases() -> list[EvalCase]:
    cases: list[EvalCase] = []
    for dataset in load_all_eval_datasets():
        cases.extend(dataset.cases)
    return cases


def merged_eval_dataset() -> EvalDataset:
    return EvalDataset(
        schema_version="1.0",
        company_name="multi",
        cases=merged_eval_cases(),
    )
