import importlib
import sys
import asyncio

import pytest

from app.core.config import Settings, get_settings
from app.services.llm_factory import build_summarizer


def test_build_summarizer_returns_groq_when_provider_is_groq():
    settings = Settings(
        LLM_PROVIDER="groq",
        GROQ_API_KEY="groq-key",
        GROQ_MODEL="llama-3.1-8b-instant",
    )

    summarizer = build_summarizer(settings)

    assert summarizer.provider == "groq"
    assert summarizer.__class__.__name__ == "GroqSummarizer"


def test_settings_defaults_prefer_groq_provider():
    assert Settings.model_fields["llm_provider"].default == "groq"
    assert Settings.model_fields["groq_model"].default == "llama-3.1-8b-instant"
    assert Settings.model_fields["gemini_model"].default == "gemini-2.5-flash"


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

    with pytest.raises(RuntimeError) as excinfo:
        build_summarizer(settings)

    message = str(excinfo.value)
    assert "groq" in message
    assert "gemini" in message


def test_build_summarizer_rejects_empty_groq_model():
    settings = Settings(
        LLM_PROVIDER="groq",
        GROQ_API_KEY="groq-key",
        GROQ_MODEL="",
    )

    with pytest.raises(RuntimeError, match="GROQ_MODEL"):
        build_summarizer(settings)


def test_build_summarizer_rejects_missing_groq_api_key():
    settings = Settings(
        LLM_PROVIDER="groq",
        GROQ_API_KEY="",
        GROQ_MODEL="llama-3.1-8b-instant",
    )

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        build_summarizer(settings)


def test_build_summarizer_rejects_whitespace_only_groq_values():
    settings = Settings(
        LLM_PROVIDER="groq",
        GROQ_API_KEY="   ",
        GROQ_MODEL="   ",
    )

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        build_summarizer(settings)


def test_build_summarizer_requires_only_active_provider_key():
    settings = Settings(
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="gemini-key",
        GEMINI_MODEL="gemini-1.5-flash",
        GROQ_API_KEY="",
        GROQ_MODEL="llama-3.1-8b-instant",
    )

    summarizer = build_summarizer(settings)

    assert summarizer.provider == "gemini"


def test_create_app_wiring_respects_llm_provider(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b-instant")

    pipeline_args = {}

    class RecordingPipeline:
        def __init__(self, *, crawler, repository, summarizer, telegram):
            pipeline_args["summarizer"] = summarizer

    monkeypatch.setattr("app.main.NewsPipeline", RecordingPipeline)

    main = importlib.import_module("app.main")
    app = main.create_app(cron_secret="top-secret")

    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/v1/trigger-crawl")
    assert route is not None
    assert pipeline_args["summarizer"].provider == "groq"
    get_settings.cache_clear()


def test_importing_app_main_is_safe_without_active_provider_credentials(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.llm_factory.build_summarizer",
        lambda settings: (_ for _ in ()).throw(RuntimeError("GROQ_API_KEY is not configured")),
    )
    sys.modules.pop("app.main", None)

    module = importlib.import_module("app.main")

    assert module.app is not None
    get_settings.cache_clear()


def test_bootstrapped_app_raises_original_startup_error(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.llm_factory.build_summarizer",
        lambda settings: (_ for _ in ()).throw(RuntimeError("GROQ_API_KEY is not configured")),
    )
    sys.modules.pop("app.main", None)

    module = importlib.import_module("app.main")

    async def enter_lifespan():
        async with module.app.router.lifespan_context(module.app):
            pass

    with pytest.raises(RuntimeError, match="GROQ_API_KEY is not configured"):
        asyncio.run(enter_lifespan())

    get_settings.cache_clear()
