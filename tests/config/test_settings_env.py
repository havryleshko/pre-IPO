from backend.config.settings import Settings


def test_settings_load_with_required_shape() -> None:
    settings = Settings(
        sec_edgar_user_agent="pre-ipo-research/1.0 (test@example.com)",
        newsapi_api_key="x",
        crunchbase_api_key="x",
        fred_api_key="x",
        twitter_bearer_token="x",
    )
    assert settings.request_timeout_seconds >= 1
    assert settings.source_cache_ttl_hours >= 1
    assert isinstance(settings.cors_origins, list)


def test_settings_parse_compose_style_cors_origins_json_string() -> None:
    settings = Settings(
        sec_edgar_user_agent="pre-ipo-research/1.0 (test@example.com)",
        cors_origins='["http://localhost:3000","http://localhost:5173"]',
    )
    assert settings.cors_origins == ["http://localhost:3000", "http://localhost:5173"]
