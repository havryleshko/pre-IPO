from tests.evals.load_gold import load_arm_round1, load_instacart_round1, load_snowflake_round1


def test_gold_arm_round1_loads() -> None:
    dataset = load_arm_round1()
    assert dataset.schema_version == "1.0"
    assert dataset.company_name == "Arm Holdings"
    assert len(dataset.cases) == 5


def test_gold_snowflake_round1_loads() -> None:
    dataset = load_snowflake_round1()
    assert dataset.schema_version == "1.0"
    assert dataset.company_name == "Snowflake"
    assert len(dataset.cases) == 5


def test_gold_instacart_round1_loads() -> None:
    dataset = load_instacart_round1()
    assert dataset.schema_version == "1.0"
    assert dataset.company_name == "Instacart"
    assert len(dataset.cases) == 2


def test_arm_contradiction_claim_ids_valid() -> None:
    dataset = load_arm_round1()
    for case in dataset.cases:
        claim_ids = {c.claim_id for c in case.claims_to_extract}
        for contradiction in case.contradictions:
            assert contradiction.claim_id in claim_ids


def test_snowflake_contradiction_claim_ids_valid() -> None:
    dataset = load_snowflake_round1()
    for case in dataset.cases:
        claim_ids = {c.claim_id for c in case.claims_to_extract}
        for contradiction in case.contradictions:
            assert contradiction.claim_id in claim_ids


def test_instacart_contradiction_claim_ids_valid() -> None:
    dataset = load_instacart_round1()
    for case in dataset.cases:
        claim_ids = {c.claim_id for c in case.claims_to_extract}
        for contradiction in case.contradictions:
            assert contradiction.claim_id in claim_ids
