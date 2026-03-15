from backend.config.settings import Settings


def test_settings_load_with_required_shape() -> None:
    settings = Settings(
        SEC_EDGAR_USER_AGENT="pre-ipo-research/1.0 (test@example.com)",
        NEWSAPI_API_KEY="x",
        CRUNCHBASE_API_KEY="x",
        FRED_API_KEY="x",
        TWITTER_BEARER_TOKEN="x",
    )
    assert settings.request_timeout_seconds >= 1
    assert settings.source_cache_ttl_hours >= 1
    assert isinstance(settings.cors_origins, list)
