from tests.evals.load_gold import load_reddit_round1


def test_gold_reddit_round1_loads() -> None:
    dataset = load_reddit_round1()
    assert dataset.schema_version == "1.0"
    assert dataset.company_name == "Reddit"
    assert len(dataset.cases) == 8


def test_gold_cases_reference_valid_claim_ids() -> None:
    dataset = load_reddit_round1()
    for case in dataset.cases:
        claim_ids = {claim.claim_id for claim in case.claims_to_extract}
        for contradiction in case.contradictions:
            assert contradiction.claim_id in claim_ids
