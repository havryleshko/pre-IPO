import pytest

from backend.agents.complexity_classifier import (
    ComplexityClassifierInput,
    classify_complexity,
)


def test_simple_tier_default_inputs() -> None:
    out = classify_complexity(ComplexityClassifierInput(company_name="SmallCo"))
    assert out.complexity_tier == "simple"
    assert len(out.active_sources) == 3
    assert "sec_edgar" in out.active_sources
    assert "news_api" in out.active_sources
    assert "crunchbase" in out.active_sources
    assert out.expected_tool_calls_per_source == (3, 5)


def test_simple_tier_low_scores() -> None:
    out = classify_complexity(
        ComplexityClassifierInput(
            company_name="TinyCo",
            has_s1_filed=False,
            media_coverage_score=39,
            source_count_hint=4,
        )
    )
    assert out.complexity_tier == "simple"
    assert len(out.active_sources) == 3


def test_standard_tier_via_has_s1_filed() -> None:
    out = classify_complexity(
        ComplexityClassifierInput(company_name="MidCo", has_s1_filed=True)
    )
    assert out.complexity_tier == "standard"
    assert len(out.active_sources) == 5
    assert out.expected_tool_calls_per_source == (5, 10)


def test_standard_tier_via_source_count_hint() -> None:
    out = classify_complexity(
        ComplexityClassifierInput(company_name="MidCo", source_count_hint=5)
    )
    assert out.complexity_tier == "standard"
    assert len(out.active_sources) == 5


def test_standard_tier_via_media_coverage() -> None:
    out = classify_complexity(
        ComplexityClassifierInput(company_name="MidCo", media_coverage_score=40)
    )
    assert out.complexity_tier == "standard"
    assert len(out.active_sources) == 5


def test_complex_tier_via_source_count_hint() -> None:
    out = classify_complexity(
        ComplexityClassifierInput(company_name="SpaceX", source_count_hint=7)
    )
    assert out.complexity_tier == "complex"
    assert len(out.active_sources) == 7
    assert set(out.active_sources) == {
        "sec_edgar",
        "rss_feeds",
        "news_api",
        "crunchbase",
        "yahoo_finance",
        "fred",
        "twitter",
    }
    assert out.expected_tool_calls_per_source == (10, 15)


def test_complex_tier_via_media_coverage() -> None:
    out = classify_complexity(
        ComplexityClassifierInput(company_name="SpaceX", media_coverage_score=80)
    )
    assert out.complexity_tier == "complex"
    assert len(out.active_sources) == 7


def test_complex_takes_precedence_over_standard() -> None:
    out = classify_complexity(
        ComplexityClassifierInput(
            company_name="BigCo",
            has_s1_filed=True,
            source_count_hint=7,
        )
    )
    assert out.complexity_tier == "complex"


def test_standard_takes_precedence_over_simple() -> None:
    out = classify_complexity(
        ComplexityClassifierInput(
            company_name="MidCo",
            has_s1_filed=True,
            media_coverage_score=10,
            source_count_hint=2,
        )
    )
    assert out.complexity_tier == "standard"
