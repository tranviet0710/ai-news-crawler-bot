from __future__ import annotations

from app.services.gemini_service import GeminiSummarizer
from app.services.openai_service import OpenAISummarizer


def build_summarizer(settings):
    provider = settings.llm_provider.lower().strip()
    if provider == "openai":
        if not settings.openai_model:
            raise RuntimeError("OPENAI_MODEL is not configured")
        return OpenAISummarizer(api_key=settings.openai_api_key, model=settings.openai_model)
    if provider == "gemini":
        if not settings.gemini_model:
            raise RuntimeError("GEMINI_MODEL is not configured")
        return GeminiSummarizer(api_key=settings.gemini_api_key, model=settings.gemini_model)
    raise RuntimeError("LLM_PROVIDER must be 'openai' or 'gemini'")
