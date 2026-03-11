from pydantic import BaseModel

from backend.models.analysis import AnalysisComplexityTier


class ComplexityClassifierInput(BaseModel):
    company_name: str
    has_s1_filed: bool = False
    media_coverage_score: int = 0
    source_count_hint: int = 0


class ComplexityClassifierOutput(BaseModel):
    complexity_tier: AnalysisComplexityTier
    active_sources: list[str]
    expected_tool_calls_per_source: tuple[int, int]


def classify_complexity(input_data: ComplexityClassifierInput) -> ComplexityClassifierOutput:
    if input_data.source_count_hint >= 7 or input_data.media_coverage_score >= 80:
        return ComplexityClassifierOutput(
            complexity_tier="complex",
            active_sources=[
                "sec_edgar",
                "rss_feeds",
                "news_api",
                "crunchbase",
                "yahoo_finance",
                "fred",
                "twitter",
            ],
            expected_tool_calls_per_source=(10, 15),
        )

    if input_data.has_s1_filed or input_data.source_count_hint >= 5 or input_data.media_coverage_score >= 40:
        return ComplexityClassifierOutput(
            complexity_tier="standard",
            active_sources=["sec_edgar", "rss_feeds", "news_api", "yahoo_finance", "fred"],
            expected_tool_calls_per_source=(5, 10),
        )

    return ComplexityClassifierOutput(
        complexity_tier="simple",
        active_sources=["sec_edgar", "news_api", "crunchbase"],
        expected_tool_calls_per_source=(3, 5),
    )
