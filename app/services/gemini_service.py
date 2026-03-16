from __future__ import annotations

from app.services.llm_prompt import PROMPT, build_news_prompt
from app.services.schemas import NewsItem, SummarizedNews


def build_gemini_client(api_key: str):
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError("google-genai package is not installed") from exc

    return genai.Client(api_key=api_key)


class GeminiSummarizer:
    provider = "gemini"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def summarize(self, item: NewsItem) -> SummarizedNews | None:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        if not self.model:
            raise RuntimeError("GEMINI_MODEL is not configured")

        client = build_gemini_client(self.api_key)
        response = client.models.generate_content(
            model=self.model,
            contents=f"{PROMPT}\n\n{build_news_prompt(item.title, item.source, item.summary, item.url)}",
        )
        text = (getattr(response, "text", "") or "").strip()
        if not text:
            raise RuntimeError("Gemini returned no usable text")
        if text.upper() == "SKIP":
            return None
        return SummarizedNews(summary=text, rationale="Accepted by Gemini filter")
