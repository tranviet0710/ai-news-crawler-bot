from app.core.config import Settings, get_settings
from app.services.llm_factory import build_summarizer
from app.services.openai_service import OpenAISummarizer


def test_build_summarizer_returns_openai_when_provider_is_openai():
    settings = Settings(
        LLM_PROVIDER="openai",
        OPENAI_API_KEY="openai-key",
        OPENAI_MODEL="gpt-4.1-mini",
    )

    summarizer = build_summarizer(settings)

    assert isinstance(summarizer, OpenAISummarizer)
    assert summarizer.provider == "openai"


def test_build_summarizer_returns_gemini_when_provider_is_gemini():
    settings = Settings(
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="gemini-key",
        GEMINI_MODEL="gemini-1.5-flash",
    )

    summarizer = build_summarizer(settings)

    assert summarizer.provider == "gemini"


def test_build_summarizer_rejects_invalid_provider():
    settings = Settings(LLM_PROVIDER="bogus")

    try:
        build_summarizer(settings)
    except RuntimeError as exc:
        assert "LLM_PROVIDER" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for invalid provider")


def test_build_summarizer_requires_only_active_provider_key():
    settings = Settings(
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="gemini-key",
        GEMINI_MODEL="gemini-1.5-flash",
        OPENAI_API_KEY="",
        OPENAI_MODEL="gpt-4.1-mini",
    )

    summarizer = build_summarizer(settings)

    assert summarizer.provider == "gemini"


def test_create_app_wiring_respects_llm_provider(monkeypatch):
    from app.main import create_app

    get_settings.cache_clear()
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-1.5-flash")
    app = create_app(cron_secret="top-secret")

    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/v1/trigger-crawl")
    assert route is not None
    get_settings.cache_clear()
