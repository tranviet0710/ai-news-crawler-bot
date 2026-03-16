from __future__ import annotations

from app.services.gemini_service import GeminiSummarizer
from app.services.groq_service import GroqSummarizer


def _is_blank(value: str) -> bool:
    return not value.strip()


def build_summarizer(settings):
    provider = settings.llm_provider.lower().strip()
    if provider == "groq":
        if _is_blank(settings.groq_api_key):
            raise RuntimeError("GROQ_API_KEY is not configured")
        if _is_blank(settings.groq_model):
            raise RuntimeError("GROQ_MODEL is not configured")
        return GroqSummarizer(api_key=settings.groq_api_key, model=settings.groq_model)
    if provider == "gemini":
        if _is_blank(settings.gemini_api_key):
            raise RuntimeError("GEMINI_API_KEY is not configured")
        if _is_blank(settings.gemini_model):
            raise RuntimeError("GEMINI_MODEL is not configured")
        return GeminiSummarizer(api_key=settings.gemini_api_key, model=settings.gemini_model)
    raise RuntimeError("LLM_PROVIDER must be 'groq' or 'gemini'")
