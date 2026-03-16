from __future__ import annotations

from app.services.llm_prompt import PROMPT, build_news_prompt
from app.services.schemas import NewsItem, SummarizedNews


def build_groq_client(api_key: str):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is not installed for Groq compatibility") from exc

    return OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")


class GroqSummarizer:
    provider = "groq"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def summarize(self, item: NewsItem) -> SummarizedNews | None:
        if not self.api_key.strip():
            raise RuntimeError("GROQ_API_KEY is not configured")
        if not self.model.strip():
            raise RuntimeError("GROQ_MODEL is not configured")

        client = build_groq_client(self.api_key)
        response = client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": PROMPT},
                {
                    "role": "user",
                    "content": build_news_prompt(item.title, item.source, item.summary, item.url),
                },
            ],
        )
        text = (response.output_text or "").strip()
        if not text:
            raise RuntimeError("Groq returned no usable text")
        if text.upper() == "SKIP":
            return None

        return SummarizedNews(summary=text, rationale="Accepted by Groq filter")
